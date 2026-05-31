// Auto-generated from data/worlds/clone_wars/maps/<>.yaml
// Regenerate via: python tools/emit_area_geometry_js.py coruscant.senate_district
window.SENATE_FIXTURE = {
  "schema_version": 1,
  "area_key": "coruscant.senate_district",
  "display_name": "SENATE DISTRICT",
  "planet": "CORUSCANT",
  "era": "20 BBY · Clone Wars",
  "default_terrain": "duracrete",
  "palette": "coruscant_senate",
  "bounds": {
    "x_min": 0.0,
    "y_min": 0.0,
    "x_max": 8.0,
    "y_max": 6.0
  },
  "districts": [
    {
      "id": "rotunda",
      "name": "SENATE ROTUNDA",
      "polygon": [
        [
          2.4,
          3.4
        ],
        [
          5.6,
          3.4
        ],
        [
          5.6,
          5.6
        ],
        [
          2.4,
          5.6
        ]
      ],
      "label_anchor": [
        3.4,
        5.4
      ],
      "rotation": 0.0
    },
    {
      "id": "processional",
      "name": "PROCESSIONAL",
      "polygon": [
        [
          2.4,
          1.8
        ],
        [
          5.6,
          1.8
        ],
        [
          5.6,
          3.4
        ],
        [
          2.4,
          3.4
        ]
      ],
      "label_anchor": [
        3.0,
        3.2
      ],
      "rotation": 0.0
    },
    {
      "id": "embassy",
      "name": "EMBASSY ROW",
      "polygon": [
        [
          5.6,
          1.4
        ],
        [
          7.6,
          1.4
        ],
        [
          7.6,
          5.6
        ],
        [
          5.6,
          5.6
        ]
      ],
      "label_anchor": [
        7.2,
        5.2
      ],
      "rotation": 0.0
    }
  ],
  "rooms": [
    {
      "id": 100,
      "name": "Rotunda Floor",
      "zone": "rotunda",
      "x": 4.0,
      "y": 4.6,
      "w": 0.9,
      "h": 0.9,
      "style": "civic",
      "symbol": "§"
    },
    {
      "id": 101,
      "name": "Pod Hall",
      "zone": "rotunda",
      "x": 4.0,
      "y": 5.4,
      "w": 0.6,
      "h": 0.4,
      "style": "civic",
      "symbol": "§"
    },
    {
      "id": 102,
      "name": "Press Gallery",
      "zone": "rotunda",
      "x": 5.0,
      "y": 4.6,
      "w": 0.5,
      "h": 0.5,
      "style": "civic",
      "symbol": "§"
    },
    {
      "id": 103,
      "name": "Speaker's Box",
      "zone": "rotunda",
      "x": 3.0,
      "y": 4.6,
      "w": 0.5,
      "h": 0.5,
      "style": "temple",
      "symbol": "T"
    },
    {
      "id": 110,
      "name": "Senate Way N",
      "zone": "processional",
      "x": 4.0,
      "y": 3.4,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·"
    },
    {
      "id": 111,
      "name": "Senate Way S",
      "zone": "processional",
      "x": 4.0,
      "y": 2.0,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·"
    },
    {
      "id": 112,
      "name": "Reflecting Pl.",
      "zone": "processional",
      "x": 3.0,
      "y": 2.6,
      "w": 0.6,
      "h": 0.5,
      "style": "landmark",
      "symbol": "※"
    },
    {
      "id": 113,
      "name": "Justice Hall",
      "zone": "processional",
      "x": 5.0,
      "y": 2.6,
      "w": 0.6,
      "h": 0.5,
      "style": "civic",
      "symbol": "§"
    },
    {
      "id": 120,
      "name": "Naboo Embassy",
      "zone": "embassy",
      "x": 6.4,
      "y": 4.8,
      "w": 0.5,
      "h": 0.5,
      "style": "housing",
      "symbol": "⌂"
    },
    {
      "id": 121,
      "name": "Alderaan Emb.",
      "zone": "embassy",
      "x": 6.4,
      "y": 4.0,
      "w": 0.5,
      "h": 0.5,
      "style": "housing",
      "symbol": "⌂"
    },
    {
      "id": 122,
      "name": "Corellia Emb.",
      "zone": "embassy",
      "x": 6.4,
      "y": 3.2,
      "w": 0.5,
      "h": 0.5,
      "style": "housing",
      "symbol": "⌂"
    },
    {
      "id": 123,
      "name": "Embassy Way",
      "zone": "embassy",
      "x": 6.4,
      "y": 2.4,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·"
    },
    {
      "id": 124,
      "name": "Senate Plaza E",
      "zone": "embassy",
      "x": 7.0,
      "y": 4.8,
      "w": 0.45,
      "h": 0.45,
      "style": "vendor",
      "symbol": "$"
    }
  ],
  "exits": [
    [
      100,
      101
    ],
    [
      100,
      102
    ],
    [
      100,
      103
    ],
    [
      100,
      110
    ],
    [
      110,
      111
    ],
    [
      110,
      112
    ],
    [
      110,
      113
    ],
    [
      111,
      123
    ],
    [
      120,
      124
    ],
    [
      120,
      121
    ],
    [
      121,
      122
    ],
    [
      122,
      123
    ]
  ],
  "exit_paths": {
    "100-110": {
      "kind": "street",
      "path": [
        [
          4.0,
          4.6
        ],
        [
          4.0,
          4.0
        ],
        [
          4.0,
          3.4
        ]
      ],
      "width": 0.3
    },
    "110-111": {
      "kind": "street",
      "path": [
        [
          4.0,
          3.4
        ],
        [
          4.0,
          2.7
        ],
        [
          4.0,
          2.0
        ]
      ],
      "width": 0.3
    },
    "120-121": {
      "kind": "road",
      "path": [
        [
          6.4,
          4.8
        ],
        [
          6.4,
          4.0
        ]
      ],
      "width": 0.22
    },
    "121-122": {
      "kind": "road",
      "path": [
        [
          6.4,
          4.0
        ],
        [
          6.4,
          3.2
        ]
      ],
      "width": 0.22
    },
    "122-123": {
      "kind": "road",
      "path": [
        [
          6.4,
          3.2
        ],
        [
          6.4,
          2.4
        ]
      ],
      "width": 0.22
    },
    "111-123": {
      "kind": "alley",
      "path": [
        [
          4.0,
          2.0
        ],
        [
          5.0,
          2.2
        ],
        [
          6.4,
          2.4
        ]
      ],
      "width": 0.18
    }
  },
  "labels": [
    {
      "text": "SENATE  WAY",
      "kind": "street",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 8.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "path_id": "100-110"
    },
    {
      "text": "EMBASSY  WAY",
      "kind": "street",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 7.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "path_id": "121-122"
    },
    {
      "text": "to Senate Floor →",
      "kind": "flavor",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 6.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "pos": [
        4.0,
        5.7
      ],
      "rot": 0.0
    }
  ],
  "landmarks": [
    {
      "id": "rotunda_dome",
      "icon": "palace",
      "name": "The Rotunda",
      "pos": [
        4.0,
        5.0
      ],
      "min_zoom": 2,
      "max_zoom": 3
    },
    {
      "id": "refl_pool",
      "icon": "beacon",
      "name": "Reflecting Pool",
      "pos": [
        3.0,
        2.6
      ],
      "min_zoom": 2,
      "max_zoom": 3
    }
  ],
  "player": {
    "room_id": 100,
    "x": 4.0,
    "y": 4.6
  },
  "contacts": []
};
