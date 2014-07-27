#!/usr/bin/env python

import irc.bot
import json
import logging
import os
import random


__CONFIG = {
    "server": "irc.quakenet.org",
    "port": 6667,
    "prefixes": "!>@.",
    "channel": "#pugbot-ng",
    "nick": "pugbot-ng",
    "owner": "",
    "size": 10,
    "maps": [
        "abbey",
        "algiers",
        "austria",
        "beijing_b3",
        "bohemia",
        "cambridge_fixed",
        "casa",
        "crossing",
        "docks",
        "dust2_v2",
        "elgin",
        "facade_b5",
        "kingdom_rc6",
        "mandolin",
        "oildepot",
        "orbital_sl",
        "prague",
        "ramelle",
        "ricochet",
        "riyadh",
        "sanctuary",
        "thingley",
        "tohunga_b8",
        "tohunga_b10",
        "toxic",
        "tunis",
        "turnpike",
        "uptown"
    ]
}


def genRandomString(length):
    alpha = "abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choice(alpha) for _ in range(length))


def _load_config():
    """
    Tries the following paths, in order, to load the json config file and
    return it as a dict:

    * `$HOME/.pugbot-ng.json`
    * `/etc/pugbot-ng.json`

    If no valid config files are found, one is automatically generated at
    `$HOME/.pugbot-ng.json`.
    """
    _HOMECONF = os.path.expanduser("~/.pugbot-ng.json")
    _TRYPATHS = [_HOMECONF,
                 "/etc/pugbot-ng.json"]
    config = {}
    while not config:
        try:
            with open(_TRYPATHS[0], "r") as configFile:
                config = json.loads(configFile.read())
        except FileNotFoundError:
            _TRYPATHS.pop(0)
        if not _TRYPATHS:
            logging.warning("Missing config file. Autogenerating default "
                            + "configuration.")
            config = __CONFIG
            with open(_HOMECONF, "w") as configFile:
                configFile.write(
                    json.dumps(__CONFIG, sort_keys=True, indent=4))
    return config


class Pugbot(irc.bot.SingleServerIRCBot):
    def __init__(self, config):
        super(Pugbot, self).__init__(
            [(config["server"], config["port"])],
            config["nick"], config["nick"])
        self.channel = config["channel"]
        self.cmdPrefixes = config["prefixes"]
        self.owner = config["owner"]
        self.password = ""
        self.pugSize = config["size"]

        self.Q = []
        self.maps = config["maps"]
        self.votes = {}

        # Adds a Latin-1 fallback when UTF-8 decoding doesn't work
        irc.client.ServerConnection.buffer_class = irc.buffer.LenientDecodingLineBuffer

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
        self.connection.privmsg(self.channel, msg)

    def pm(self, nick, msg):
        self.connection.privmsg(nick, msg)

    def on_welcome(self, conn, e):
        conn.join(self.channel)

        self.password = genRandomString(5)
        self.lastpass = self.password

        print("The password is: " + self.password)
        if self.owner:
            self.pm(self.owner, "The password is: " + self.password)

    def new_password(self):

        if self.lastpass == self.password:
            self.password = genRandomString(5)
            self.lastpass = self.password

        print("The password is: " + self.password)
        if self.owner:
            self.pm(self.owner, "The password is: " + self.password)

    def on_privmsg(self, conn, e):
        if (e.arguments[0][0] in self.cmdPrefixes):
            self.executeCommand(conn, e)

    def on_pubmsg(self, conn, e):
        if (e.arguments[0][0] in self.cmdPrefixes):
            self.executeCommand(conn, e)

    def executeCommand(self, conn, e):
        issuedBy = e.source.nick
        text = e.arguments[0][1:].split(" ")
        command = text[0].lower()
        data = " ".join(text[1:])

        if (data[:5] == self.password):
            pref = "pw_cmd_"
        else:
            pref = "cmd_"

        try:
            commandFunc = getattr(self, pref + command)
            commandFunc(issuedBy, data)
        except AttributeError:
            self.notice(issuedBy, "Command not found: " + command)

    """
    #------------------------------------------#
    #               Other Stuff                #
    #------------------------------------------#
    """

    def _on_nick(self, conn, ev):
        old = ev.source.nick
        new = ev.target

        if old in self.Q:
            self.Q.remove(old)
            self.Q.append(new)

        if old in self.votes:
            self.votes[new] = self.votes[old]
            self.votes.pop(old)

    def removeUser(self, user):
        if user in self.Q:
            self.Q.remove(user)
            self.say("{0} was removed from the queue".format(user))

        if user in self.votes:
            self.votes.pop(user)

    def _on_part(self, conn, ev):
        self.removeUser(ev.source.nick)

    def _on_quit(self, conn, ev):
        self.removeUser(ev.source.nick)

    def startGame(self):
        if len(self.Q) < 2:
            self.say("A game cannot be started with fewer than 2 players.")
            return

        mapVotes = self.votes.values()

        if not mapVotes:
            mapVotes = self.maps

        maxVotes = max([mapVotes.count(mapname) for mapname in mapVotes])
        mapPool = [mapname for mapname in mapVotes
                   if mapVotes.count(mapname) == maxVotes]

        chosenMap = mapPool[random.randint(0, len(mapPool) - 1)]

        captains = random.sample(self.Q, 2)

        self.say("\x030,2Ding ding ding! The PUG is starting! The map is "
                 + chosenMap)
        self.say("\x030,2The captains are {0} and {1}!".format(
            captains[0], captains[1]))
        self.say("\x037Players: " + ", ".join(self.Q))

        self.Q = []
        self.votes = {}

    def resolveMap(self, string):
        matches = []

        if not string:
            return matches

        for m in self.maps:
            if string in m:
                matches.append(m)
        return matches

    def voteHelper(self, player, string):
        mapMatches = self.resolveMap(string)

        if not string:
            return

        if not mapMatches:
            self.notice(player, "{0} is not a valid map".format(string))
        elif len(mapMatches) > 1:
            self.notice(player,
                        "There are multiple matches for '{0}': ".format(string)
                        + ", ".join(mapMatches))
        else:
            self.votes[player] = mapMatches[0]
            self.say("{0} voted for {1}".format(player, mapMatches[0]))

    """
    #------------------------------------------#
    #                Commands                  #
    #------------------------------------------#
    """

    def cmd_help(self, issuedBy, data):
        """.help [command] - displays this message"""
        if data == "":
            attrs = sorted(dir(self))
            self.notice(issuedBy, "Commands:")
            for attr in attrs:
                if attr[:4] == "cmd_":
                    self.notice(issuedBy, getattr(self, attr).__doc__)
        else:
            try:
                command = getattr(self, "cmd_" + data.lower())
                self.notice(issuedBy, command.__doc__)
            except AttributeError:
                self.notice(issuedBy, "Command not found: " + data)

    def cmd_join(self, issuedBy, data):
        """.join - joins the queue"""
        if issuedBy not in self.Q:
            self.Q.append(issuedBy)
            self.say("{0} was added to the queue".format(issuedBy))
        else:
            self.notice(issuedBy, "You are already in the queue")

        self.voteHelper(issuedBy, data)

        if len(self.Q) == self.pugSize:
            self.startGame()

    def cmd_leave(self, issuedBy, data):
        """.leave - leaves the queue"""
        if issuedBy in self.Q:
            self.Q.remove(issuedBy)
            self.votes.pop(issuedBy, None)
            self.say("{0} was removed from the queue".format(issuedBy))
        else:
            self.notice(issuedBy, "You are not in the queue")

    def cmd_status(self, issuedBy, data):
        """.status - displays the status of the current queue"""
        if len(self.Q) == 0:
            self.notice(issuedBy, "Queue is empty: 0/{0}".format(self.pugSize))
            return

        self.notice(issuedBy,
                    "Queue status: {0}/{1}".format(len(self.Q), self.pugSize))
        self.notice(issuedBy, ", ".join(self.Q))

    def cmd_maps(self, issuedBy, data):
        """.maps - list maps that are able to be voted"""
        self.notice(issuedBy, "Available maps: " + ", ".join(self.maps))

    def cmd_vote(self, issuedBy, data):
        """.vote - vote for a map"""
        if issuedBy not in self.Q:
            self.notice(issuedBy, "You are not in the queue")
        else:
            self.voteHelper(issuedBy, data)

    def cmd_votes(self, issuedBy, data):
        """.votes - show number of votes per map"""

        mapvotes = self.votes.values()
        tallies = dict((map, mapvotes.count(map)) for map in mapvotes)

        if self.votes:
            for map in tallies:
                self.notice(issuedBy, "{0}: {1} vote{2}".format(
                    map, tallies[map], "" if tallies[map] == 1 else "s"))
        else:
            self.notice(issuedBy, "There are no current votes")

    def pw_cmd_plzdie(self, issuedBy, data):
        """.plzdie - kills the bot"""
        self.die("{0} doesn't like me :<".format(issuedBy))

    def pw_cmd_forcestart(self, issuedBy, data):
        """.forcestart - starts the game regardless of whether there are enough
        players or not"""
        self.say("{0} is forcing the game to start!".format(issuedBy))
        self.startGame()
        self.new_password()


def main():

    _config = _load_config()
    bot = Pugbot(_config)
    bot.start()

if __name__ == "__main__":
    main()
