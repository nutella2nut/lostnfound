from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from inventory.models import UserRoleChangeLog

User = get_user_model()


@override_settings(
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class UserManagementAccessTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "superadmin", "super@tisb.ac.in", "pass1234"
        )
        self.admin = User.objects.create_user(
            "staffadmin", "staff@tisb.ac.in", "pass1234", is_staff=True
        )
        self.client = Client()

    def test_superuser_can_access_list(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("inventory:user_management_list"))
        self.assertEqual(resp.status_code, 200)

    def test_admin_cannot_access_list(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("inventory:user_management_list"))
        self.assertNotEqual(resp.status_code, 200)

    def test_anonymous_cannot_access_list(self):
        resp = self.client.get(reverse("inventory:user_management_list"))
        self.assertNotEqual(resp.status_code, 200)


@override_settings(
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class UserManagementCreateTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "superadmin", "super@tisb.ac.in", "pass1234"
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_create_admin_user(self):
        resp = self.client.post(
            reverse("inventory:user_management_create"),
            {
                "username": "newadmin",
                "first_name": "New",
                "last_name": "Admin",
                "email": "newadmin@tisb.ac.in",
                "role": "admin",
                "is_active": True,
                "password": "StrongPass123!",
                "send_welcome_email": False,
            },
        )
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="newadmin")
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        # Should have a role change log
        self.assertEqual(
            UserRoleChangeLog.objects.filter(
                target_user=user, action="CREATE"
            ).count(),
            1,
        )

    def test_create_superuser(self):
        self.client.post(
            reverse("inventory:user_management_create"),
            {
                "username": "newsuper",
                "first_name": "New",
                "last_name": "Super",
                "email": "newsuper@tisb.ac.in",
                "role": "superuser",
                "is_active": True,
                "password": "StrongPass123!",
            },
        )
        user = User.objects.get(username="newsuper")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)  # §6.6 rule 4

    def test_non_tisb_email_rejected(self):
        resp = self.client.post(
            reverse("inventory:user_management_create"),
            {
                "username": "baduser",
                "first_name": "Bad",
                "last_name": "User",
                "email": "bad@gmail.com",
                "role": "admin",
                "is_active": True,
                "password": "StrongPass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)  # re-renders form
        self.assertFalse(User.objects.filter(username="baduser").exists())

    def test_duplicate_username_rejected(self):
        resp = self.client.post(
            reverse("inventory:user_management_create"),
            {
                "username": "superadmin",  # existing
                "first_name": "Dup",
                "last_name": "User",
                "email": "dup@tisb.ac.in",
                "role": "admin",
                "is_active": True,
                "password": "StrongPass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)  # re-renders form
        self.assertEqual(User.objects.filter(username="superadmin").count(), 1)

    def test_case_insensitive_duplicate_username_rejected(self):
        resp = self.client.post(
            reverse("inventory:user_management_create"),
            {
                "username": "SuperAdmin",  # case-insensitive match
                "first_name": "Dup",
                "last_name": "User",
                "email": "dup@tisb.ac.in",
                "role": "admin",
                "is_active": True,
                "password": "StrongPass123!",
            },
        )
        self.assertEqual(resp.status_code, 200)


@override_settings(
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class UserManagementEditTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "superadmin", "super@tisb.ac.in", "pass1234",
            first_name="Super", last_name="Admin",
        )
        self.other_super = User.objects.create_superuser(
            "othersuper", "other@tisb.ac.in", "pass1234",
            first_name="Other", last_name="Super",
        )
        self.admin = User.objects.create_user(
            "staffadmin", "staff@tisb.ac.in", "pass1234", is_staff=True,
            first_name="Staff", last_name="Admin",
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_promote_admin_to_superuser(self):
        self.client.post(
            reverse("inventory:user_management_edit", args=[self.admin.pk]),
            {
                "first_name": self.admin.first_name,
                "last_name": self.admin.last_name,
                "email": self.admin.email,
                "role": "superuser",
                "is_active": True,
            },
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)
        self.assertTrue(self.admin.is_staff)  # auto-set

    def test_cannot_demote_self(self):
        resp = self.client.post(
            reverse("inventory:user_management_edit", args=[self.superuser.pk]),
            {
                "first_name": self.superuser.first_name,
                "last_name": self.superuser.last_name,
                "email": self.superuser.email,
                "role": "admin",
                "is_active": True,
            },
        )
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)  # unchanged

    def test_cannot_demote_last_superuser(self):
        # Remove the other superuser
        self.other_super.delete()
        resp = self.client.post(
            reverse("inventory:user_management_edit", args=[self.superuser.pk]),
            {
                "first_name": self.superuser.first_name,
                "last_name": self.superuser.last_name,
                "email": self.superuser.email,
                "role": "admin",
                "is_active": True,
            },
        )
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)

    def test_edit_creates_role_change_log(self):
        self.client.post(
            reverse("inventory:user_management_edit", args=[self.admin.pk]),
            {
                "first_name": "Updated",
                "last_name": self.admin.last_name,
                "email": self.admin.email,
                "role": "superuser",
                "is_active": True,
            },
        )
        self.assertTrue(
            UserRoleChangeLog.objects.filter(
                target_user=self.admin, action="PROMOTE_SUPERUSER"
            ).exists()
        )


@override_settings(
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class UserManagementDeleteTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "superadmin", "super@tisb.ac.in", "pass1234"
        )
        self.other_super = User.objects.create_superuser(
            "othersuper", "other@tisb.ac.in", "pass1234"
        )
        self.admin = User.objects.create_user(
            "staffadmin", "staff@tisb.ac.in", "pass1234", is_staff=True
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_cannot_delete_self(self):
        resp = self.client.post(
            reverse("inventory:user_management_delete", args=[self.superuser.pk]),
            {"confirm_username": "superadmin"},
        )
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())

    def test_delete_requires_username_confirmation(self):
        resp = self.client.post(
            reverse("inventory:user_management_delete", args=[self.admin.pk]),
            {"confirm_username": "wrong_name"},
        )
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_delete_with_correct_confirmation(self):
        resp = self.client.post(
            reverse("inventory:user_management_delete", args=[self.admin.pk]),
            {"confirm_username": "staffadmin"},
        )
        self.assertFalse(User.objects.filter(username="staffadmin").exists())
        # Log preserved
        self.assertTrue(
            UserRoleChangeLog.objects.filter(
                target_username_snapshot="staffadmin", action="DELETE"
            ).exists()
        )

    def test_cannot_delete_last_active_superuser(self):
        # Delete the other superuser first, leaving only self
        self.other_super.delete()
        # Now try to delete self — should fail
        resp = self.client.post(
            reverse("inventory:user_management_delete", args=[self.superuser.pk]),
            {"confirm_username": "superadmin"},
        )
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())

    def test_deletion_preserves_log_rows(self):
        # Create a log entry for the admin
        UserRoleChangeLog.objects.create(
            target_user=self.admin,
            target_username_snapshot="staffadmin",
            performed_by=self.superuser,
            performed_by_username_snapshot="superadmin",
            action="PROMOTE_ADMIN",
        )
        # Delete admin
        self.client.post(
            reverse("inventory:user_management_delete", args=[self.admin.pk]),
            {"confirm_username": "staffadmin"},
        )
        # Log still exists with null target_user
        log = UserRoleChangeLog.objects.get(
            target_username_snapshot="staffadmin", action="PROMOTE_ADMIN"
        )
        self.assertIsNone(log.target_user)


@override_settings(
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class UserManagementSetPasswordTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "superadmin", "super@tisb.ac.in", "pass1234"
        )
        self.admin = User.objects.create_user(
            "staffadmin", "staff@tisb.ac.in", "pass1234", is_staff=True
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_set_password(self):
        new_pw = "NewStrongPass456!"
        self.client.post(
            reverse("inventory:user_management_set_password", args=[self.admin.pk]),
            {"password": new_pw},
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password(new_pw))

    def test_set_password_creates_log(self):
        self.client.post(
            reverse("inventory:user_management_set_password", args=[self.admin.pk]),
            {"password": "NewPass123!"},
        )
        self.assertTrue(
            UserRoleChangeLog.objects.filter(
                target_user=self.admin, action="PASSWORD_RESET"
            ).exists()
        )
