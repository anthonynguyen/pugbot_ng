import json
import logging
import os

__CONFIG = {
    "server": "irc.quakenet.org",
    "port": 6667,
    "prefixes": "!>@.",
    "channel": "#pugbot-ng",
    "nick": "pugbot-ng",
    "owners": [
        ""
    ],
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


def load_config():
    """
    Tries the following paths, in order, to load the json config file and
    return it as a dict:

    * `$HOME/.pugbot-ng.json`
    * `/etc/pugbot_ng.json`

    If no valid config files are found, one is automatically generated at
    `$HOME/.pugbot_ng.json`.
    """
    _HOMECONF = os.path.expanduser("~/.pugbot_ng.json")
    _TRYPATHS = [_HOMECONF,
                 "/etc/pugbot_ng.json"]
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
