import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

log = logging.getLogger(__name__)


def send_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    message = (
        f"Salom, {user.full_name}!\n\n"
        f"FindIt hisobingiz (@{user.username}) uchun parolni tiklash so'rovi keldi.\n"
        f"Yangi parol o'rnatish uchun havolani oching (havola {minutes} daqiqa amal qiladi):\n\n"
        f"{link}\n\n"
        "Agar bu so'rovni siz yubormagan bo'lsangiz, xatni e'tiborsiz qoldiring: parolingiz o'zgarmaydi."
    )
    try:
        send_mail("FindIt: parolni tiklash", message, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        # Xato foydalanuvchiga ko'rsatilmaydi (hisob bor-yo'qligi oshkor bo'lmasligi uchun)
        log.exception("Parolni tiklash xati yuborilmadi: user=%s", user.pk)