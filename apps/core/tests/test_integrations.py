import importlib.util
import pathlib
from io import StringIO

import pytest
from django.core.management import call_command
from django.urls import reverse


@pytest.mark.django_db
def test_coop_allows_google_signin_popup(client):
    # ค่าเริ่มต้นของ Django (same-origin) ทำให้ popup ของ Google ส่งผลล็อกอินกลับมาไม่ได้
    assert client.get(reverse('accounts:login'))['Cross-Origin-Opener-Policy'] == 'same-origin-allow-popups'


def test_check_integrations_never_prints_secrets(settings):
    settings.EASYSLIP_API_KEY = 'super-secret-easyslip-key-123'
    settings.GOOGLE_MAPS_API_KEY = 'AIza' + 'x' * 35
    settings.PROMPTPAY_ID = '0812345678'
    settings.FIREBASE_CREDENTIALS_PATH = ''
    out = StringIO()
    call_command('check_integrations', stdout=out)
    text = out.getvalue()
    assert 'super-secret-easyslip-key-123' not in text and 'AIza' not in text
    assert 'สร้าง QR ได้' in text and 'xxxxxx5678' in text


def _load_set_env(tmp_path):
    spec = importlib.util.spec_from_file_location('set_env', pathlib.Path('deploy/set_env.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ENV_PATH = tmp_path / '.env'
    return module


def test_set_env_merges_file_and_deletes_it(tmp_path, capsys):
    set_env = _load_set_env(tmp_path)
    set_env.ENV_PATH.write_text('A=1\nFIREBASE_API_KEY=\n# comment\n')
    snippet = tmp_path / 'fb.env'
    snippet.write_text('# x\nFIREBASE_API_KEY=abc=def\nNEW_KEY="quoted"\nbad key=1\n')
    set_env.main(['--from-file', str(snippet)])
    text = set_env.ENV_PATH.read_text()
    assert 'FIREBASE_API_KEY=abc=def' in text and 'NEW_KEY=quoted' in text and 'A=1' in text
    assert 'bad key' not in text and not snippet.exists()
    assert oct(set_env.ENV_PATH.stat().st_mode)[-3:] == '600'


def test_set_env_status_hides_secret_values(tmp_path, capsys):
    set_env = _load_set_env(tmp_path)
    set_env.ENV_PATH.write_text('EASYSLIP_API_KEY=topsecret\nSITE_URL=https://tmth-th.com\nPROMPTPAY_ID=\n')
    set_env.main(['--status'])
    out = capsys.readouterr().out
    assert 'topsecret' not in out and 'ตั้งแล้ว (ยาว 9)' in out
    assert 'https://tmth-th.com' in out and '(ว่าง)' in out
