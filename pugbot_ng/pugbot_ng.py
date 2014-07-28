#!/usr/bin/env python

from . import config_loader
import irc.bot
import random


def genRandomString(length):
    alpha = "abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choice(alpha) for _ in range(length))

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
        self.parseChat(conn, ev)

    def on_pubmsg(self, conn, ev):
        self.parseChat(conn, ev)

    def parseChat(self, conn, ev):
        if (ev.arguments[0][0] in self.state.cmdPrefixes):
            self.commandHandler.executeCommand(conn, ev)

    """
    #------------------------------------------#
    #               Other Stuff                #
    #------------------------------------------#
    """

    def startGame(self):
        if len(self.state.Q) < 2:
            self.say("A game cannot be started with fewer than 2 players.")
            return

        mapVotes = self.state.votes.values()

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

class PugState():
    def __init__(self, config):
        self.server = config["server"]
        self.port = config["port"]

        self.nick = config["nick"]
        self.channel = config["channel"]

        self.cmdPrefixes = config["prefixes"]
        self.owners = config["owners"]
        self.pugSize = config["size"]

        self.password = ""

        self.Q = []
        self.maps = config["maps"]
        self.votes = {}

        self.loggedIn = []


class CommandHandler():
    def __init__(self, bot):
        self.bot = bot
        self.state = bot.state

    def executeCommand(self, conn, ev):
        issuedBy = ev.source.nick
        text = ev.arguments[0][1:].split(" ")
        command = text[0].lower()
        data = " ".join(text[1:])

        found = False

        try:
            commandFunc = getattr(self, "cmd_" + command)
            commandFunc(issuedBy, data)
            found = True
        except AttributeError:
            if data[:5] == self.state.password or issuedBy in self.state.loggedIn:
                try:
                    commandFunc = getattr(self, "pw_cmd_" + command)
                    commandFunc(issuedBy, data)
                    found = True
                except AttributeError:
                    pass
        
        if not found:
            self.bot.notice(issuedBy, "Command not found: " + command)

    """
    #------------------------------------------#
    #             Command Helpers              #
    #------------------------------------------#
    """

    def resolveMap(self, string):
        matches = []

        if not string:
            return matches

        for m in self.state.maps:
            if string in m:
                matches.append(m)
        return matches

    def voteHelper(self, player, string):
        mapMatches = self.resolveMap(string)

        if not string:
            return

        if not mapMatches:
            self.bot.notice(player, "{0} is not a valid map".format(string))
        elif len(mapMatches) > 1:
            self.bot.notice(player,
                        "There are multiple matches for '{0}': ".format(string)
                        + ", ".join(mapMatches))
        else:
            self.state.votes[player] = mapMatches[0]
            self.bot.say("{0} voted for {1}".format(player, mapMatches[0]))


    """
    #------------------------------------------#
    #                Commands                  #
    #------------------------------------------#
    """

    def cmd_help(self, issuedBy, data):
        """.help [command] - displays this message"""
        if data == "":
            attrs = sorted(dir(self))
            self.bot.notice(issuedBy, "Commands:")
            for attr in attrs:
                if attr[:4] == "cmd_":
                    self.bot.notice(issuedBy, getattr(self, attr).__doc__)
        else:
            try:
                command = getattr(self, "cmd_" + data.lower())
                self.bot.notice(issuedBy, command.__doc__)
            except AttributeError:
                self.bot.notice(issuedBy, "Command not found: " + data)

    def cmd_join(self, issuedBy, data):
        """.join - joins the queue"""
        if issuedBy not in self.state.Q:
            self.state.Q.append(issuedBy)
            self.bot.say("{0} was added to the queue".format(issuedBy))
        else:
            self.bot.notice(issuedBy, "You are already in the queue")

        self.voteHelper(issuedBy, data)

        if len(self.state.Q) == self.state.pugSize:
            self.bot.startGame()

    def cmd_leave(self, issuedBy, data):
        """.leave - leaves the queue"""
        if issuedBy in self.state.Q:
            self.state.Q.remove(issuedBy)
            self.state.votes.pop(issuedBy, None)
            self.bot.say("{0} was removed from the queue".format(issuedBy))
        else:
            self.bot.notice(issuedBy, "You are not in the queue")

    def cmd_status(self, issuedBy, data):
        """.status - displays the status of the current queue"""
        if len(self.state.Q) == 0:
            self.bot.notice(issuedBy, "Queue is empty: 0/{0}".format(self.state.pugSize))
            return

        self.bot.notice(issuedBy,
                    "Queue status: {0}/{1}".format(len(self.state.Q), self.state.pugSize))
        self.bot.notice(issuedBy, ", ".join(self.state.Q))

    def cmd_maps(self, issuedBy, data):
        """.maps - list maps that are able to be voted"""
        self.bot.notice(issuedBy, "Available maps: " + ", ".join(self.state.maps))

    def cmd_vote(self, issuedBy, data):
        """.vote - vote for a map"""
        if issuedBy not in self.state.Q:
            self.bot.notice(issuedBy, "You are not in the queue")
        else:
            self.voteHelper(issuedBy, data)

    def cmd_votes(self, issuedBy, data):
        """.votes - show number of votes per map"""

        mapvotes = self.state.votes.values()
        tallies = dict((map, mapvotes.count(map)) for map in mapvotes)

        if self.state.votes:
            for map in tallies:
                self.bot.notice(issuedBy, "{0}: {1} vote{2}".format(
                    map, tallies[map], "" if tallies[map] == 1 else "s"))
        else:
            self.bot.notice(issuedBy, "There are no current votes")

    def pw_cmd_login(self, issuedBy, data):
        """.login - logs you in"""
        if issuedBy not in self.state.loggedIn:
            self.state.loggedIn.append(issuedBy)
            self.bot.notice(issuedBy, "You have successfully logged in")
        else:
            self.bot.notice(issuedBy, "You are already logged in")

    def pw_cmd_plzdie(self, issuedBy, data):
        """.plzdie - kills the bot"""
        self.bot.die("{0} doesn't like me :<".format(issuedBy))

    def pw_cmd_forcestart(self, issuedBy, data):
        """.forcestart - starts the game regardless of whether there are enough
        players or not"""
        self.bot.say("{0} is forcing the game to start!".format(issuedBy))
        self.bot.startGame()
        self.bot.new_password()



def main():
    state = PugState(config_loader.load_config())
    bot = Pugbot(state)
    bot.start()

if __name__ == "__main__":
    main()
