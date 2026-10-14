"""Optional browser regression, always isolated from the local user database."""
import os
import subprocess
import tempfile
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core import signing
from django.test import override_settings

from .models import User
from . import tests as existing


@skipUnless(os.getenv('PROJECTUS_BROWSER_TESTS') == '1', 'Set PROJECTUS_BROWSER_TESTS=1 to run Chromium')
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class VueBrowserTests(StaticLiveServerTestCase):
    setUp = existing.ProjectusTests.setUp

    def test_browser_scenarios(self):
        user = User.objects.create_user('verify@example.com', 'VeryStrongPass!241')
        token = signing.dumps({'user': user.pk, 'nonce': str(user.verification_nonce)}, salt='verify-email')
        environment = {**os.environ, 'PROJECTUS_TEST_URL': self.live_server_url,
                       'PROJECTUS_VERIFY_PATH': f'/email/verify/{token}/'}
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            result = subprocess.run(['npm', 'run', 'test:browser'], cwd=settings.BASE_DIR,
                                    env=environment, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
