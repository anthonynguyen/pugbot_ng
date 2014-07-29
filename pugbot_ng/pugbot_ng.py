#!/usr/bin/env python

from . import config_loader
from .command_handler import CommandHandler
from .pug_state import PugState
from .util import genRandomString
import irc.bot
import random


class Pugbot(irc.bot.SingleServerIRCBot):

    def __init__(self, state):
        super(Pugbot, self).__init__(
            [(state.server, state.port)],
            state.nick, state.nick)

        self.state = state

        # Adds a Latin-1 fallback when UTF-8 decoding doesn't work
        irc.client.ServerConnection.buffer_class = irc.buffer.LenientDecodingLineBuffer

        self.commandHandler = CommandHandler(self)

    """
    #------------------------------------------#
    #            IRC-Related Stuff             #
    #------------------------------------------#
    """

    def notice(self, nick, msg):
        self.connection.notice(nick, msg)

    def on_nicknameinuse(self, conn, ev):
        conn.nick(conn.get_nickname() + "_")

    def on_ping(self, conn, ev):
        self.connection.pong(ev.target)

    def say(self, msg):
        self.connection.privmsg(self.state.channel, msg)

    def pm(self, nick, msg):
        self.connection.privmsg(nick, msg)

    def on_welcome(self, conn, ev):
        conn.join(self.state.channel)
        self.new_password()

    """
    #------------------------------------------#
    #                Commands                  #
    #------------------------------------------#
    """

    def on_privmsg(self, conn, ev):
        self.parseChat(ev)

    def on_pubmsg(self, conn, ev):
        self.parseChat(ev)
        if self.state.password in ev.arguments[0]:
            self.new_password()

    def parseChat(self, ev):
        if (ev.arguments[0][0] in self.state.cmdPrefixes):
            self.commandHandler.executeCommand(ev)

    """
    #------------------------------------------#
    #               Other Stuff                #
    #------------------------------------------#
    """

    def startGame(self):
        if len(self.state.Q) < 2:
            self.say("A game cannot be started with fewer than 2 players.")
            return

        mapVotes = list(self.state.votes.values())

        if not mapVotes:
            mapVotes = self.state.maps

        maxVotes = max([mapVotes.count(mapname) for mapname in mapVotes])
        mapPool = [mapname for mapname in mapVotes
                   if mapVotes.count(mapname) == maxVotes]

        chosenMap = mapPool[random.randint(0, len(mapPool) - 1)]

        captains = random.sample(self.state.Q, 2)

        self.say("\x030,2Ding ding ding! The PUG is starting! The map is "
                 + chosenMap)
        self.say("\x030,2The captains are {0} and {1}!".format(
            captains[0], captains[1]))
        self.say("\x037Players: " + ", ".join(self.state.Q))

        self.state.Q = []
        self.state.votes = {}

    def new_password(self):
        self.state.password = genRandomString(5)

        print("The password is: " + self.state.password)
        self._msg_owners("The password is: " + self.state.password)

    def _msg_owners(self, message):
        for owner in self.state.owners:
            self.pm(owner, message)

    def removeUser(self, user):
        if user in self.state.Q:
            self.state.Q.remove(user)
            self.say("{0} was removed from the queue".format(user))

        if user in self.state.votes:
            self.state.votes.pop(user)

        if user in self.state.loggedIn:
            self.state.loggedIn.remove(user)

    def _on_nick(self, conn, ev):
        old = ev.source.nick
        new = ev.target

        if old in self.state.Q:
            self.state.Q.remove(old)
            self.state.Q.append(new)

        if old in self.state.votes:
            self.state.votes[new] = self.state.votes[old]
            self.state.votes.pop(old)

        if old in self.state.loggedIn:
            self.state.loggedIn.remove(old)
            self.state.loggedIn.append(new)

    def _on_part(self, conn, ev):
        self.removeUser(ev.source.nick)

    def _on_quit(self, conn, ev):
        self.removeUser(ev.source.nick)


def main():
    state = PugState(config_loader.load_config())
    bot = Pugbot(state)
    bot.start()

if __name__ == "__main__":
    main()
