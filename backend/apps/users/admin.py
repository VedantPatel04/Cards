from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import CustomUser


class LockedDownUserAdmin(UserAdmin):
    """
    Privilege lockdown for /admin/:

    - is_superuser is never grantable or revocable via the admin UI.
      Bootstrap superusers with `createsuperuser` / manage.py only.
    - Only superusers may edit is_staff, groups, and user_permissions.
    - The last remaining superuser cannot be deleted from admin.
    """

    list_display = ("username", "first_name", "last_name", "is_staff")
    search_fields = ("username", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "usable_password", "password1", "password2"),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if "is_superuser" not in readonly:
            readonly.append("is_superuser")
        if not request.user.is_superuser:
            for field in ("is_staff", "is_active", "groups", "user_permissions"):
                if field not in readonly:
                    readonly.append(field)
        return readonly

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        # Non-superuser staff: hide permission-granting fieldsets entirely.
        safe = []
        for name, opts in fieldsets:
            fields = opts.get("fields", ())
            if "is_superuser" in fields or "user_permissions" in fields:
                continue
            if "groups" in fields and "is_staff" in fields:
                continue
            safe.append((name, opts))
        return safe

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser:
            other_supers = CustomUser.objects.filter(is_superuser=True).exclude(
                pk=obj.pk
            )
            if not other_supers.exists():
                return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        # Defense in depth: never elevate/demote superuser via admin saves.
        if change:
            previous = CustomUser.objects.filter(pk=obj.pk).values_list(
                "is_superuser", flat=True
            ).first()
            if previous is not None:
                obj.is_superuser = previous
        else:
            obj.is_superuser = False
        if not request.user.is_superuser:
            if change:
                prev = CustomUser.objects.filter(pk=obj.pk).first()
                if prev is not None:
                    obj.is_staff = prev.is_staff
                    obj.is_active = prev.is_active
            else:
                obj.is_staff = False
        super().save_model(request, obj, form, change)


admin.site.register(CustomUser, LockedDownUserAdmin)
