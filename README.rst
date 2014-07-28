pugbot_ng
=========

pugbot-ng = pugbot next gen

Commands:

* ``help``
* ``plzdie``
* ``forcestart``
* ``join`` or ``join <mapname>``
* ``leave``
* ``status``
* ``maps``
* ``vote <mapname>``
* ``votes``

Configuration
-------------

Configuration is handled by a JSON file, located in either `/etc/pugbot_ng.json`
or `$HOME/.pugbot_ng.json`. An example configuration file is as follows::

    {
        "channel": "#pugbot-ng",
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
        ],
        "nick": "pugbot-ng",
        "owners": [
            "foo",
            "bar"
        ],
        "port": 6667,
        "prefixes": "!>@.",
        "server": "irc.quakenet.org",
        "size": 10
    }

Discussion
----------

Please report bugs using `GitHub Issues`_.

You can also join ``#pugbot-ng`` on `Quakenet`_ to ask questions or get involved.

.. _`GitHub Issues`: https://github.com/clearskies/pugbot_ng/issues
.. _`Quakenet`: https://www.quakenet.org/
