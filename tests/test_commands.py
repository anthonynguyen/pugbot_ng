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
        self.state.Q = []
        testQueue = []
        self.handler.cmd_join("user1", "")
        testQueue.append("user1")
        self.assertEqual(self.state.Q, testQueue)
        self.bot.say.assert_called_with("user1 was added to the queue")

        self.handler.cmd_join("user1", "")
        self.assertEqual(self.state.Q, testQueue)
        self.bot.notice.assert_called_with("user1", "You are already in the queue")
       
        self.handler.cmd_join("user2", "")
        testQueue.append("user2")
        self.assertEqual(self.state.Q, testQueue)
        self.bot.say.assert_called_with("user2 was added to the queue")

        self.handler.cmd_join("user3", "blah")
        testQueue.append("user3")
        self.assertEqual(self.state.Q, testQueue)
        self.bot.say.assert_called_with("user3 was added to the queue")
        self.bot.notice.assert_called_with("user3", "blah is not a valid map")

        self.handler.cmd_join("user3", "town")
        self.assertEqual(self.state.Q, testQueue)
        self.bot.say.assert_called_with("user3 voted for uptown")
        self.assertEqual(self.state.votes, {"user3": "uptown"})

    def test_leave(self):
        self.state.Q = ["user1"]

        self.handler.cmd_leave("user1", "")
        self.assertEqual(self.state.Q, [])
        self.bot.say.assert_called_with("user1 was removed from the queue")

        self.handler.cmd_leave("user1", "")
        self.bot.notice.assert_called_with("user1", "You are not in the queue")

    def test_status(self):
        self.state.Q = ["user1", "user2", "user3"]

        self.handler.cmd_status("user1", "")
        self.bot.notice.assert_has_calls([
            unittest.mock.call("user1", "Queue status: 3/10"),
            unittest.mock.call("user1", "user1, user2, user3")
        ])

        self.state.Q = []
        self.handler.cmd_status("user1", "")
        self.bot.notice.assert_called_with("user1", "Queue is empty: 0/10")

    def test_maps(self):
        self.handler.cmd_maps("user1", "")
        self.bot.notice.assert_called_with("user1", "Available maps: abbey, uptown")

if __name__ == "__main__":
    unittest.main()
