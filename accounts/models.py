from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Role(models.TextChoices):
    USER = "USER", "Foydalanuvchi"
    MODERATOR = "MODERATOR", "Moderator"
    ADMIN = "ADMIN", "Admin"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, password, **extra):
        if not username:
            raise ValueError("Username majburiy")
        email = self.normalize_email(extra.pop("email", ""))
        user = self.model(username=username, email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, password=None, **extra):
        extra.setdefault("role", Role.USER)
        return self._create_user(username, password, **extra)

    def create_superuser(self, username, password=None, **extra):
        extra["role"] = Role.ADMIN
        return self._create_user(username, password, **extra)


class User(AbstractUser):
    # username, email (ixtiyoriy) va parol AbstractUser'dan keladi
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)

    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    @property
    def is_moderator(self):
        return self.role in (Role.MODERATOR, Role.ADMIN)

    def save(self, *args, **kwargs):
        # Django admin'ga kirish va huquqlar rolga qarab belgilanadi
        self.is_staff = self.role in (Role.MODERATOR, Role.ADMIN)
        self.is_superuser = self.role == Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} (@{self.username})"