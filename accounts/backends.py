from django.contrib.auth.backends import BaseBackend

from .models import User


class KakaoBackend(BaseBackend):
    def authenticate(self, request, kakao_id=None, **kwargs):
        if kakao_id is None:
            return None
        try:
            return User.objects.get(kakao_id=kakao_id)
        except User.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
