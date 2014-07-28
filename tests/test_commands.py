#!/usr/bin/env python

from pugbot_ng.pugbot_ng import CommandHandler, PugState

import unittest
import unittest.mock

class CommandTest(unittest.TestCase):
    def setUp(self):
        config = {
            "channel": "#pugbot-ng",
            "maps": [
                "abbey",
                "uptown"
            ],
            "nick": "pugbot-ng",
            "owners": [
                "bar"
            ],
            "port": 6667,
            "prefixes": "!>@.",
            "server": "irc.quakenet.org",
            "size": 10
        }

        self.bot = unittest.mock.Mock()
        self.handler = CommandHandler(self.bot)
        self.state = PugState(config)
        self.handler.state = self.state

    def test_join(self):
        testQueue = []
        self.handler.cmd_join("user1", "")
        testQueue.append("user1")
        self.assertEqual(self.state.Q, testQueue)

        self.handler.cmd_join("user2", "")
        testQueue.append("user2")
        self.assertEqual(self.state.Q, testQueue)
       
if __name__ == "__main__":
    unittest.main()
