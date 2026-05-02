from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    # Map to the existing 'password_hash' column in the users table.
    # AbstractBaseUser declares `password`; overriding with db_column preserves compatibility.
    password = models.CharField(max_length=255, db_column="password_hash")

    email = models.EmailField(max_length=255, unique=True)
    role = models.CharField(max_length=32, default="member")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        app_label = "accounts"

    def __str__(self):
        return self.email

    @property
    def is_staff(self):
        return self.role == "admin"

    @property
    def is_superuser(self):
        return self.role == "admin"

    def has_perm(self, perm, obj=None):
        return self.role == "admin"

    def has_module_perms(self, app_label):
        return self.role == "admin"
