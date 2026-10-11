import sys
import unittest
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import tests.testdb  # noqa: E402,F401  (must come before any api import)
import psycopg  # noqa: E402
import api.auth as auth  # noqa: E402
import api.rides as rides  # noqa: E402
import tests.test_auth as base  # noqa: E402

PASSWORD = base.PASSWORD
VALID_RIDE = {
    "pickup_location": "Airport",
    "dropoff_location": "Downtown Hotel",
    "pickup_time": "2030-01-15T14:30",
    "notes": "Two passengers, one large bag",
}


def user_id(connection, username):
    user = auth._get_user_by_username(connection, username)
    assert user is not None, f"No user named {username!r}"
    return user.id


class RideStorageTests(base.DatabaseTestCase):
    def setUp(self):
        super().setUp()
        auth.create_user(self.connection, "boss", PASSWORD, role="admin")
        self.admin_id = user_id(self.connection, "boss")

    def create(self, **overrides):
        values = {
            "pickup_location": "A",
            "dropoff_location": "B",
            "pickup_time": datetime(2030, 1, 1, 10, 0),
            "notes": "",
            "created_by": self.admin_id,
            **overrides,
        }
        return rides.create_ride(self.connection, **values)

    def test_create_ride_returns_id_and_stores_all_fields(self):
        ride_id = self.create(
            pickup_location="Airport",
            dropoff_location="Hotel",
            pickup_time=datetime(2030, 1, 15, 14, 30),
            notes="One bag",
        )

        [ride] = rides.list_rides(self.connection)
        self.assertEqual(ride.id, ride_id)
        self.assertEqual(ride.pickup_location, "Airport")
        self.assertEqual(ride.dropoff_location, "Hotel")
        self.assertEqual(ride.pickup_time, datetime(2030, 1, 15, 14, 30))
        self.assertEqual(ride.notes, "One bag")
        self.assertEqual(ride.created_by, self.admin_id)

    def test_new_rides_are_available(self):
        self.create()

        self.assertTrue(rides.list_rides(self.connection)[0].available)

    def test_availability_is_stored_as_a_real_boolean_column(self):
        self.create()

        self.assertIs(
            self.connection.execute("SELECT available FROM rides").fetchone()[0], True)
        self.connection.execute("UPDATE rides SET available = FALSE")
        self.assertFalse(rides.list_rides(self.connection)[0].available)

    def test_rides_are_listed_by_pickup_time(self):
        self.create(pickup_location="late", pickup_time=datetime(2030, 3, 1, 9, 0))
        self.create(pickup_location="early", pickup_time=datetime(2030, 1, 1, 9, 0))
        self.create(pickup_location="middle", pickup_time=datetime(2030, 2, 1, 9, 0))

        self.assertEqual(
            [ride.pickup_location for ride in rides.list_rides(self.connection)],
            ["early", "middle", "late"],
        )

    def test_no_rides_gives_an_empty_list(self):
        self.assertEqual(rides.list_rides(self.connection), [])

    def test_ride_must_belong_to_an_existing_user(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            self.create(created_by=9999)
        self.connection.rollback()


class AdminWebTestCase(base.WebTestCase):
    def login_as(self, username, role):
        auth.create_user(self.connection, username, PASSWORD, role=role)
        response = self.login(username)
        self.assertEqual(response.status_code, 303)

    def login_admin(self):
        self.login_as("boss", "admin")

    def stored_rides(self):
        return rides.list_rides(self.connection)

    def create_ride(self, **overrides):
        return self.post_form("/admin/rides", page="/admin", **{**VALID_RIDE, **overrides})


class AdminAccessTests(AdminWebTestCase):
    def test_anonymous_visitor_is_redirected_to_login(self):
        for method, url in (("get", "/admin"), ("post", "/admin/rides")):
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url)

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/login")

    def test_driver_gets_403_on_dashboard(self):
        self.login_as("alice", "driver")

        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_driver_cannot_create_a_ride(self):
        self.login_as("alice", "driver")
        # A driver cannot load the form, so reuse a token from another page
        token = self.csrf_token("/account")

        response = self.client.post(
            "/admin/rides", data={"csrf_token": token, **VALID_RIDE})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.stored_rides(), [])

    def test_anonymous_post_is_redirected_and_creates_nothing(self):
        token = self.csrf_token("/login")

        for data in (VALID_RIDE, {}):
            with self.subTest(fields=len(data)):
                response = self.client.post(
                    "/admin/rides", data={"csrf_token": token, **data})

                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], "/login")
        self.assertEqual(self.stored_rides(), [])

    def test_invalid_session_cookie_is_redirected_to_login(self):
        self.client.cookies.set(base.AUTH_COOKIE, "not-a-jwt")

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")

    def test_admin_sees_the_dashboard_with_a_csrf_protected_form(self):
        self.login_admin()

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/admin/rides"', response.text)
        self.assertRegex(response.text, base.CSRF_FIELD)
        for field in ("pickup_location", "dropoff_location", "pickup_time", "notes"):
            self.assertIn(f'name="{field}"', response.text)
        self.assertIn("No ride requests yet.", response.text)

    def test_admin_link_is_shown_only_to_admins(self):
        self.login_as("alice", "driver")
        driver_home = self.client.get("/account")
        self.client.cookies.clear()
        self.login_admin()
        admin_home = self.client.get("/account")

        self.assertNotIn('href="/admin"', driver_home.text)
        self.assertIn('href="/admin"', admin_home.text)


class CreateRideTests(AdminWebTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def test_admin_creates_a_ride_and_is_redirected(self):
        response = self.create_ride()

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/admin?created=true")
        [ride] = self.stored_rides()
        self.assertEqual(ride.pickup_location, "Airport")
        self.assertEqual(ride.dropoff_location, "Downtown Hotel")
        self.assertEqual(ride.pickup_time, datetime(2030, 1, 15, 14, 30))
        self.assertEqual(ride.notes, "Two passengers, one large bag")

    def test_ride_records_the_admin_who_created_it(self):
        self.create_ride()

        [ride] = self.stored_rides()
        self.assertEqual(ride.created_by, user_id(self.connection, "boss"))

    def test_new_ride_is_available_and_shown_as_available(self):
        self.create_ride()

        self.assertTrue(self.stored_rides()[0].available)
        self.assertIn("Available", self.client.get("/admin").text)
        self.assertIn("text-bg-success", self.client.get("/admin").text)

    def test_unavailable_ride_is_shown_as_not_available(self):
        self.create_ride()
        self.connection.execute("UPDATE rides SET available = FALSE")
        self.connection.commit()

        page = self.client.get("/admin")

        self.assertIn("text-bg-secondary", page.text)
        self.assertNotIn("text-bg-success", page.text)

    def test_available_cannot_be_set_through_the_form(self):
        self.create_ride(available="false")

        self.assertTrue(self.stored_rides()[0].available)

    def test_created_ride_is_listed_on_the_dashboard(self):
        self.create_ride()

        page = self.client.get("/admin?created=true")

        self.assertIn("Ride request created.", page.text)
        for text in ("Airport", "Downtown Hotel", "2030-01-15 14:30", "one large bag"):
            self.assertIn(text, page.text)
        self.assertNotIn("No ride requests yet.", page.text)

    def test_notes_are_optional(self):
        response = self.create_ride(notes="")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.stored_rides()[0].notes, "")

    def test_notes_field_may_be_left_out_entirely(self):
        fields = {k: v for k, v in VALID_RIDE.items() if k != "notes"}

        response = self.post_form("/admin/rides", page="/admin", **fields)

        self.assertEqual(response.status_code, 303)

    def test_surrounding_whitespace_is_trimmed(self):
        self.create_ride(
            pickup_location="  Airport  ", dropoff_location=" Hotel ", notes="  hi  ")

        [ride] = self.stored_rides()
        self.assertEqual(
            (ride.pickup_location, ride.dropoff_location, ride.notes),
            ("Airport", "Hotel", "hi"),
        )

    def test_accepts_times_with_seconds(self):
        response = self.create_ride(pickup_time="2030-01-15T14:30:45")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self.stored_rides()[0].pickup_time, datetime(2030, 1, 15, 14, 30, 45))

    def test_maximum_length_values_are_accepted(self):
        response = self.create_ride(
            pickup_location="p" * 200, dropoff_location="d" * 200, notes="n" * 1024)

        self.assertEqual(response.status_code, 303)

    def test_each_ride_is_stored_separately(self):
        self.create_ride(pickup_location="First")
        self.create_ride(pickup_location="Second", pickup_time="2030-01-10T08:00")

        self.assertEqual(
            [ride.pickup_location for ride in self.stored_rides()], ["Second", "First"])

    def test_markup_in_values_is_escaped_on_the_dashboard(self):
        self.create_ride(
            pickup_location="<script>alert(1)</script>", notes="<b>bold</b>")

        page = self.client.get("/admin")

        self.assertNotIn("<script>alert(1)</script>", page.text)
        self.assertNotIn("<b>bold</b>", page.text)
        self.assertIn("&lt;script&gt;", page.text)


class InvalidRideTests(AdminWebTestCase):
    def setUp(self):
        super().setUp()
        self.login_admin()

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 422)
        self.assertIn("Enter a pickup and drop-off location", response.text)
        self.assertEqual(self.stored_rides(), [])

    def test_missing_or_blank_required_fields_are_rejected(self):
        cases = {
            "blank pickup": {"pickup_location": ""},
            "spaces only pickup": {"pickup_location": "   "},
            "blank drop-off": {"dropoff_location": ""},
            "spaces only drop-off": {"dropoff_location": "   "},
            "blank time": {"pickup_time": ""},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                self.assert_rejected(self.create_ride(**overrides))

    def test_missing_fields_are_rejected(self):
        for missing in ("pickup_location", "dropoff_location", "pickup_time"):
            with self.subTest(missing=missing):
                fields = {k: v for k, v in VALID_RIDE.items() if k != missing}

                self.assert_rejected(
                    self.post_form("/admin/rides", page="/admin", **fields))

    def test_invalid_pickup_times_are_rejected(self):
        for value in ("tomorrow", "2030-13-45T25:61", "2030-02-30T10:00", "10:30"):
            with self.subTest(value=value):
                self.assert_rejected(self.create_ride(pickup_time=value))

    def test_time_zone_aware_pickup_times_are_rejected(self):
        for value in ("2030-01-15T14:30Z", "2030-01-15T14:30:00+02:00"):
            with self.subTest(value=value):
                self.assert_rejected(self.create_ride(pickup_time=value))

    def test_over_long_values_are_rejected(self):
        for overrides in (
            {"pickup_location": "p" * 201},
            {"dropoff_location": "d" * 201},
            {"notes": "n" * 1025},
        ):
            with self.subTest(field=list(overrides)):
                self.assert_rejected(self.create_ride(**overrides))

    def test_form_keeps_what_was_typed(self):
        response = self.create_ride(pickup_time="tomorrow", notes="Keep me")

        self.assertIn('value="Airport"', response.text)
        self.assertIn('value="Downtown Hotel"', response.text)
        self.assertIn('value="tomorrow"', response.text)
        self.assertIn("Keep me", response.text)

    def test_echoed_values_are_capped_and_escaped(self):
        response = self.create_ride(
            pickup_location="x" * 5000, notes="<script>alert(1)</script>" + "n" * 5000)

        self.assertEqual(response.status_code, 422)
        self.assertNotIn("x" * 201, response.text)
        self.assertNotIn("n" * 1000, response.text)
        self.assertNotIn("<script>alert(1)</script>", response.text)

    def test_rejected_page_still_lists_existing_rides_and_has_a_fresh_token(self):
        self.create_ride(pickup_location="Existing")

        response = self.create_ride(pickup_location="")

        self.assertIn("Existing", response.text)
        self.assertRegex(response.text, base.CSRF_FIELD)

    def test_bad_csrf_token_is_rejected(self):
        self.client.get("/admin")

        response = self.client.post(
            "/admin/rides", data={"csrf_token": "forged", **VALID_RIDE})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.stored_rides(), [])

    def test_missing_csrf_token_is_rejected(self):
        self.client.get("/admin")

        response = self.client.post("/admin/rides", data=VALID_RIDE)

        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(self.stored_rides(), [])

    def test_there_is_no_json_route_for_creating_rides(self):
        for url in ("/api/rides", "/api/create_ride", "/rides", "/admin/rides.json"):
            with self.subTest(url=url):
                response = self.client.post(url, json=VALID_RIDE)

                self.assertIn(response.status_code, (404, 405))
        self.assertEqual(self.stored_rides(), [])


if __name__ == "__main__":
    unittest.main()
