import unittest
from proxy_trust import client_ip, docker_gateways


class ProxyTrustTests(unittest.TestCase):
    def test_chains_and_spoofing(self):
        trust = lambda value: value in {'127.0.0.1', '::1', '172.18.0.1'}
        cases = [
            ('127.0.0.1', '198.51.100.8', '198.51.100.8'),
            ('::ffff:127.0.0.1', '198.51.100.8', '198.51.100.8'),
            ('127.0.0.1', '1.2.3.4, 198.51.100.8', '198.51.100.8'),
            ('198.51.100.8', '1.2.3.4', '198.51.100.8'),
            ('172.18.0.9', '1.2.3.4', '172.18.0.9'),
            ('127.0.0.1', 'bad-ip, 198.51.100.8', '127.0.0.1'),
            ('127.0.0.1', '2001:db8::8', '2001:db8::8'),
            ('127.0.0.1', '', '127.0.0.1'),
        ]
        for peer, header, expected in cases:
            with self.subTest(peer=peer, header=header):
                self.assertEqual(client_ip(peer, header, trust), expected)

    def test_gateway_is_one_address(self):
        self.assertEqual(docker_gateways('eth0 00000000 010012AC 0003\neth1 00FB1EAC 00000000 0001'), {'172.18.0.1'})
