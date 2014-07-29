#!/usr/bin/env python

from pugbot_ng.pugbot_ng import CommandHandler, PugState

import unittest
import unittest.mock

class CommandTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        config = {
            "channel": "#pugbot-ng",
            "maps": [
                "abbey",
                "turnpike",
                "uptown"
            ],
            "nick": "pugbot-ng",
            "owners": [
                "bar"
            ],
            "port": 6667,
            "prefixes": "!>@.",
            "server": "irc.quakenet.org",
            "size": 10,
            "urt_servers": [
                {
                    "host": "example.com",
                    "port": 27960,
                    "password": "rconpassword"
                }
            ]
        }


        self.bot = unittest.mock.Mock()
        self.handler = CommandHandler(self.bot)
        self.state = PugState(config)
        self.handler.state = self.state

    def setUp(self):
        self.bot.reset_mock()
        self.state.Q = []
        self.state.votes = {}

    def test_join(self):
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
        ], any_order = True)

        self.state.Q = []
        self.handler.cmd_status("user1", "")
        self.bot.notice.assert_called_with("user1", "Queue is empty: 0/10")

    def test_maps(self):
        self.handler.cmd_maps("user1", "")
        self.bot.notice.assert_called_with("user1", "Available maps: abbey, turnpike, uptown")

    def test_vote(self):
        self.handler.cmd_vote("user1", "")
        self.bot.notice.assert_called_with("user1", "You are not in the queue")

        self.state.Q = ["user1"]
        
        self.handler.cmd_vote("user1", "asd")
        self.bot.notice.assert_called_with("user1", "asd is not a valid map")

        self.handler.cmd_vote("user1", "u")
        self.bot.notice.assert_called_with("user1", "There are multiple matches for 'u': turnpike, uptown")

        self.state.votes = {}
        self.handler.cmd_vote("user1", "turn")
        self.assertEqual(self.state.votes, {"user1": "turnpike"})
        self.bot.say.assert_called_with("user1 voted for turnpike")
    
    def test_votes(self):
        self.handler.cmd_votes("user1", "")
        self.bot.notice.assert_called_with("user1", "There are no current votes")

        self.state.votes = {"user1": "turnpike"}
        self.handler.cmd_votes("user1", "")
        self.bot.notice.assert_called_with("user1", "turnpike: 1 vote")

        self.state.votes = {"user1": "turnpike", "user2": "turnpike"}
        self.handler.cmd_votes("user1", "")
        self.bot.notice.assert_called_with("user1", "turnpike: 2 votes")

        self.bot.notice.reset_mock()

        self.state.votes = {"user1": "turnpike", "user2": "uptown", "user3": "uptown", "user4": "abbey"}
        self.handler.cmd_votes("user1", "")
        self.bot.notice.assert_has_calls([
            unittest.mock.call("user1", "uptown: 2 votes"),
            unittest.mock.call("user1", "turnpike: 1 vote"),
            unittest.mock.call("user1", "abbey: 1 vote")
        ], any_order = True)

if __name__ == "__main__":
    unittest.main()
