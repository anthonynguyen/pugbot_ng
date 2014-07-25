#!/usr/bin/env python

import irc.bot
import json

class Pugbot(irc.bot.SingleServerIRCBot):
    def __init__(self, server, port, prefixes, channel, nick):
        super(Pugbot, self).__init__([(server, port)], nick, nick)
        self.channel = channel
        self.target = self.channel
        self.cmdPrefixes = prefixes

    def say(self, msg):
        self.connection.privmsg(self.channel, msg)

    def pm(self, nick, msg):
        self.connection.privmsg(nick, msg)
    
    def reply(self, msg):
        self.connection.privmsg(self.target, msg)

    def on_welcome(self, conn, e):
        conn.join(self.channel)

    def on_privmsg(self, conn, e):
        self.executeCommand(conn, e, True)

    def on_pubmsg(self, conn, e):
        if (e.arguments[0][0] in self.cmdPrefixes):
            self.executeCommand(conn, e)

    def executeCommand(self, conn, e, private = False):
        issuedBy = e.source.nick
        text = e.arguments[0][1:].split(" ")
        command = text[0].lower()
        data = text[1:]

        if private:
            self.target = issuedBy
        else:
            self.target = self.channel

        try:
            commandFunc = getattr(self, "cmd_" + command)
            commandFunc(issuedBy, data)
        except AttributeError:
            self.reply("Command not found: " + command)

    
    def cmd_plzdie(self, issuedBy, data):
        self.die("{} doesn't like me :<".format(issuedBy))

    def cmd_hello(self, issuedBy, data):
        self.reply("Hello, {}!".format(issuedBy))

if __name__ == "__main__":
    try:
        configFile = open("config.json", "r")
        config = json.loads(configFile.read())
    except IOError:
        config = {
            "server": "irc.quakenet.org",
            "port": 6667,
            "prefixes": "!@>.",
            "channel": "#nuubs",
            "nick": "pugbot-ng"
        }

    bot = Pugbot(config["server"], config["port"], config["prefixes"], config["channel"], config["nick"])
    bot.start()
