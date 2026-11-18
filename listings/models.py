from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MaxValueValidator, MinValueValidator


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Lucide ikon nomi, masalan: smartphone")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Kategoriya"
        verbose_name_plural = "Kategoriyalar"

    def __str__(self):
        return self.name


class Location(models.Model):
    class Type(models.TextChoices):
        UNIVERSITY = "UNIVERSITY", "Universitet"
        MALL = "MALL", "Savdo markazi"
        LIBRARY = "LIBRARY", "Kutubxona"
        AIRPORT = "AIRPORT", "Aeroport"
        STATION = "STATION", "Vokzal / bekat"
        OTHER = "OTHER", "Boshqa"

    name = models.CharField(max_length=150)
    type = models.CharField(max_length=12, choices=Type.choices, default=Type.OTHER)
    city = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True,
                                 validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(null=True, blank=True,
                                  validators=[MinValueValidator(-180), MaxValueValidator(180)])
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Joy"
        verbose_name_plural = "Joylar"

    def __str__(self):
        return self.name


class Listing(models.Model):
    class Type(models.TextChoices):
        LOST = "LOST", "Yo'qolgan"
        FOUND = "FOUND", "Topilgan"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Tekshiruvda"
        ACTIVE = "ACTIVE", "Faol"
        REJECTED = "REJECTED", "Rad etilgan"
        IN_CLAIM = "IN_CLAIM", "Da'vo ko'rilmoqda"
        CLOSED = "CLOSED", "Yopilgan"

    type = models.CharField(max_length=5, choices=Type.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listings")
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True)

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=40, blank=True)
    brand = models.CharField(max_length=80, blank=True)
    place_detail = models.CharField(max_length=200, blank=True)
    event_date = models.DateField(help_text="Yo'qolgan yoki topilgan sana")
    image = models.ImageField(upload_to="listings/", null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True,
                                 validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(null=True, blank=True,
                                  validators=[MinValueValidator(-180), MaxValueValidator(180)])
    details = models.JSONField(default=dict, blank=True, help_text="Kategoriyaga xos qo'shimcha maydonlar")

    # Faqat FOUND uchun. Ommaga ko'rsatilmaydi, da'vo tekshiruvida ishlatiladi.
    secret_detail = models.TextField(blank=True, verbose_name="Yashirin belgi")
    storage_place = models.CharField(max_length=200, blank=True, verbose_name="Saqlanayotgan joy")

    reject_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "E'lon"
        verbose_name_plural = "E'lonlar"
        indexes = [models.Index(fields=["type", "status"])]

    def clean(self):
        errors = {}
        if self.status == self.Status.REJECTED and not self.reject_reason.strip():
            errors["reject_reason"] = "Rad etish sababini yozing."
        if (self.latitude is None) != (self.longitude is None):
            errors["longitude"] = "Kenglik va uzunlik birga kiritilishi kerak."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.Status.CLOSED and not self.closed_at:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.type}] {self.title}"


class Match(models.Model):
    class Status(models.TextChoices):
        SUGGESTED = "SUGGESTED", "Taklif qilingan"
        DISMISSED = "DISMISSED", "Rad etilgan"
        CONFIRMED = "CONFIRMED", "Tasdiqlangan"

    lost_listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="matches_as_lost")
    found_listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="matches_as_found")
    score = models.DecimalField(max_digits=5, decimal_places=2)
    reasons = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUGGESTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(fields=["lost_listing", "found_listing"], name="uq_match_pair"),
        ]
        verbose_name = "Moslik"
        verbose_name_plural = "Mosliklar"

    def __str__(self):
        return f"{self.lost_listing_id} ~ {self.found_listing_id} ({self.score})"


class Claim(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Kutilmoqda"
        APPROVED = "APPROVED", "Tasdiqlangan"
        REJECTED = "REJECTED", "Rad etilgan"

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="claims",
                                help_text="Da'vo qilinayotgan FOUND e'loni")
    match = models.ForeignKey(Match, on_delete=models.SET_NULL, null=True, blank=True, related_name="claims")
    claimant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="claims")
    proof_text = models.TextField(verbose_name="Egalik isboti")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    review_note = models.TextField(blank=True, verbose_name="Moderator izohi")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="reviewed_claims")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # Bitta e'longa bir vaqtda faqat bitta faol da'vo
            models.UniqueConstraint(
                fields=["listing"],
                condition=models.Q(status__in=["PENDING", "APPROVED"]),
                name="uq_active_claim_per_listing",
            ),
        ]
        verbose_name = "Da'vo"
        verbose_name_plural = "Da'volar"

    @transaction.atomic
    def approve(self, moderator):
        """Da'vo tasdiqlanadi: topilgan e'lon (va mos yo'qolgan e'lon) yopiladi."""
        now = timezone.now()
        self.status = self.Status.APPROVED
        self.reviewed_by, self.reviewed_at = moderator, now
        self.save()
        self.listing.status = Listing.Status.CLOSED
        self.listing.save()
        if self.match:
            self.match.status = Match.Status.CONFIRMED
            self.match.save()
            lost = self.match.lost_listing
            lost.status = Listing.Status.CLOSED
            lost.save()

    @transaction.atomic
    def reject(self, moderator):
        """Da'vo rad etiladi: topilgan e'lon yana faol bo'ladi."""
        self.status = self.Status.REJECTED
        self.reviewed_by, self.reviewed_at = moderator, timezone.now()
        self.save()
        self.listing.status = Listing.Status.ACTIVE
        self.listing.save()
        if self.match:
            self.match.status = Match.Status.DISMISSED
            self.match.save()

    def __str__(self):
        return f"Da'vo #{self.pk} -> {self.listing_id}"


class FoundReport(models.Model):
    """Yo'qolgan (LOST) e'longa "men topdim" arizasi. Ommaviy e'lon emas."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Kutilmoqda"
        APPROVED = "APPROVED", "Tasdiqlangan"
        REJECTED = "REJECTED", "Rad etilgan"
        COMPLETED = "COMPLETED", "Topshirilgan"

    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="found_reports",
                                help_text="Yo'qolgan (LOST) e'lon")
    finder = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="found_reports")
    message = models.TextField(verbose_name="Qayerda va qanday topildi")
    current_place = models.CharField(max_length=200, blank=True, verbose_name="Buyum hozir qayerda")
    contact = models.CharField(max_length=100, blank=True, verbose_name="Bog'lanish uchun")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    review_note = models.TextField(blank=True, verbose_name="Moderator izohi")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="reviewed_reports")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "finder"],
                condition=models.Q(status__in=["PENDING", "APPROVED"]),
                name="uq_active_report_per_finder",
            ),
        ]
        verbose_name = "Topilma arizasi"
        verbose_name_plural = "Topilma arizalari"

    @transaction.atomic
    def approve(self, moderator):
        """Tasdiqlandi: e'lon egasiga topuvchi ma'lumotlari ko'rinadi."""
        self.status = self.Status.APPROVED
        self.reviewed_by, self.reviewed_at = moderator, timezone.now()
        self.save()
        self.listing.status = Listing.Status.IN_CLAIM
        self.listing.save()

    @transaction.atomic
    def reject(self, moderator):
        self.status = self.Status.REJECTED
        self.reviewed_by, self.reviewed_at = moderator, timezone.now()
        self.save()

    @transaction.atomic
    def dispute(self):
        """E'lon egasi "bu mening buyumim emas" dedi: e'lon yana faol."""
        self.status = self.Status.REJECTED
        self.review_note = (self.review_note + " Egasi tasdiqlamadi.").strip()
        self.save()
        self.listing.status = Listing.Status.ACTIVE
        self.listing.save()

    @transaction.atomic
    def complete(self):
        """E'lon egasi buyumni oldi: e'lon yopiladi."""
        self.status = self.Status.COMPLETED
        self.save()
        self.listing.status = Listing.Status.CLOSED
        self.listing.save()

    def __str__(self):
        return f"Ariza #{self.pk} -> {self.listing_id}"