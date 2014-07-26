#!/usr/bin/env python

import irc.bot
import json
import random

def genRandomString(length):
    alpha = "abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choice(alpha) for _ in range(length))

class Pugbot(irc.bot.SingleServerIRCBot):
    def __init__(self, config):
        super(Pugbot, self).__init__([(config["server"], config["port"])], config["nick"], config["nick"])
        self.channel = config["channel"]
        self.target = self.channel
        self.cmdPrefixes = config["prefixes"]
        self.owner = config["owner"]
        self.password = ""
        self.pugSize = config["size"]

        self.Q = []
        self.maps = ["abbey", "algiers", "austria", "bohemia", "casa", "docks", "dressingroom", "eagle", "elgin", "kingdom", "kingdom_rc6", "mandolin", "prague", "riyadh", "sanc", "snoppis", "subway", "swim", "thingley", "tunis", "turnpike", "uptown"]
        self.votes = {}

        # Adds a Latin-1 fallback when UTF-8 decoding doesn't work
        irc.client.ServerConnection.buffer_class = irc.buffer.LenientDecodingLineBuffer
    
    def on_ping(self, conn, ev):
        self.connection.pong(ev.target)

    def say(self, msg):
        self.connection.privmsg(self.channel, msg)

    def pm(self, nick, msg):
        self.connection.privmsg(nick, msg)
    
    def reply(self, msg):
        self.connection.privmsg(self.target, msg)

    def on_welcome(self, conn, e):
        conn.join(self.channel)

        self.password = genRandomString(5)

        print("The password is: " + self.password)
        if self.owner:
            self.pm(self.owner, "The password is: " + self.password)

    def on_privmsg(self, conn, e):
        self.executeCommand(conn, e, True)

    def on_pubmsg(self, conn, e):
        if (e.arguments[0][0] in self.cmdPrefixes):
            self.executeCommand(conn, e)

    def executeCommand(self, conn, e, private = False):
        issuedBy = e.source.nick
        text = e.arguments[0][1:].split(" ")
        command = text[0].lower()
        data = " ".join(text[1:])

        if private:
            self.target = issuedBy
        else:
            self.target = self.channel

        if (data[:5] == self.password):
            pref = "pw_cmd_"
        else:
            pref = "cmd_"

        try:
            commandFunc = getattr(self, pref + command)
            commandFunc(issuedBy, data)
        except AttributeError:
            self.reply("Command not found: " + command)

    def cmd_help(self, issuedBy, data):
        """.help [command] - displays this message"""
        if data == "":
            attrs = sorted(dir(self))
            self.reply("Commands:")
            for attr in attrs:
                if attr[:4] == "cmd_":
                    self.reply(getattr(self, attr).__doc__)
        else:
            try:
                command = getattr(self, "cmd_" + data.lower())
                self.reply(command.__doc__)
            except AttributeError:
                self.reply("Command not found: " + data)
    
    def pw_cmd_plzdie(self, issuedBy, data):
        """.plzdie - kills the bot"""
        self.die("{0} doesn't like me :<".format(issuedBy))
    
    def cmd_join(self, issuedBy, data):
        """.join - joins the queue"""
        if issuedBy not in self.Q:
            self.Q.append(issuedBy)
            self.say("{0} was added to the queue".format(issuedBy))
        else:
            self.reply("You are already in the queue")

        if len(self.Q) == self.pugSize:
            self.say("\x034,2Ding ding ding, the PUG is starting!")
            self.Q = []
            self.votes = {}

    def cmd_leave(self, issuedBy, data):
        """.leave - leaves the queue"""
        if issuedBy in self.Q:
            self.Q.remove(issuedBy)
            self.say("{0} was removed from the queue".format(issuedBy))
        else:
            self.reply("You are not in the queue")

    def cmd_status(self, issuedBy, data):
        """.status - displays the queue status"""
        if len(self.Q) == 0:
            self.reply("Queue is empty: 0/{0}".format(self.pugSize))
            return

        self.reply("Queue status: {0}/{1}".format(len(self.Q), self.pugSize))
        self.reply(", ".join(self.Q))

    def cmd_maps(self, issuedBy, data):
        """.maps - list maps that are able to be voted"""
        self.say("Maps: abbey, algiers, austria, bohemia, casa, docks, dressingroom, eagle, elgin, kingdom, kingdom_rc6, mandolin, prague, riyadh, sanc, snoppis, subway, swim, thingley, tunis, turnpike, uptown")

    def cmd_vote(self, issuedBy, data):
        """.vote - vote for a map"""
        if issuedBy not in self.Q:
            self.reply("You are not in the queue")
        else:
            if data not in self.maps:
                self.reply("{0} is not a valid map".format(data))
        
            if data in self.maps:
                self.votes[issuedBy] = data
                self.say("{0} voted for {1}".format(issuedBy, data))

    def cmd_votes(self, issuedBy, data):
        """.votes - show number of votes per map"""

        mapvotes = self.votes.values()
        tallies = dict((map, mapvotes.count(map)) for map in mapvotes)

        if self.votes:
            for map in tallies:
                self.reply("{0}: {1} vote{2}".format(map, tallies[map], "" if tallies[map] == 1 else "s"))
        else:
            self.reply("There are no current votes")

def main():
    try:
        configFile = open("config.json", "r")
        config = json.loads(configFile.read())
    except:
        print("Invalid or missing config file. Check if config.json exists and follows the correct format")
        return

    bot = Pugbot(config)
    bot.start()

if __name__ == "__main__":
    main()
