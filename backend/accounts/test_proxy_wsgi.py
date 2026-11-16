from django.test import SimpleTestCase

from config.proxy_wsgi import trusted_proxy


def remote_addr(**environ):
    seen = {}

    def app(env, start_response):
        seen['ip'] = env.get('REMOTE_ADDR')
        return []

    trusted_proxy(app)({'REMOTE_ADDR': '172.18.0.5', **environ}, None)
    return seen['ip']


class TrustedProxyTests(SimpleTestCase):
    """Login throttling keys on REMOTE_ADDR, so a client must not be able to choose it."""

    def test_takes_address_appended_by_nginx(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR='203.0.113.7'), '203.0.113.7')

    def test_ignores_client_supplied_entries(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR='1.2.3.4, 9.9.9.9 , 203.0.113.7'), '203.0.113.7')

    def test_keeps_socket_peer_without_header(self):
        self.assertEqual(remote_addr(), '172.18.0.5')
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR=' , '), '172.18.0.5')

    def test_keeps_socket_peer_for_malformed_value(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR='1.2.3.4, not-an-ip'), '172.18.0.5')

    def test_normalises_ipv6(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR='2001:DB8::0:1'), '2001:db8::1')
