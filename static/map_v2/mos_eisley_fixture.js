// Auto-generated from data/worlds/clone_wars/maps/<>.yaml
// Regenerate via: python tools/emit_area_geometry_js.py tatooine.mos_eisley
window.MOS_EISLEY_FIXTURE = {
  "schema_version": 1,
  "area_key": "tatooine.mos_eisley",
  "display_name": "MOS EISLEY",
  "planet": "TATOOINE",
  "era": "20 BBY · Clone Wars",
  "default_terrain": "sand",
  "palette": "tatooine",
  "bounds": {
    "x_min": 2.4,
    "y_min": -0.4,
    "x_max": 14.8,
    "y_max": 7.6
  },
  "districts": [
    {
      "id": "spaceport",
      "name": "SPACEPORT",
      "polygon": [
        [
          3.4,
          3.6
        ],
        [
          7.4,
          3.6
        ],
        [
          7.4,
          7.4
        ],
        [
          3.4,
          7.4
        ]
      ],
      "label_anchor": [
        6.6,
        7.0
      ],
      "rotation": 0.0
    },
    {
      "id": "market",
      "name": "MARKET QUARTER",
      "polygon": [
        [
          3.4,
          2.4
        ],
        [
          7.4,
          2.4
        ],
        [
          7.4,
          3.6
        ],
        [
          3.4,
          3.6
        ]
      ],
      "label_anchor": [
        6.9,
        3.5
      ],
      "rotation": 0.0
    },
    {
      "id": "cantina",
      "name": "CANTINA ROW",
      "polygon": [
        [
          2.4,
          1.4
        ],
        [
          3.4,
          1.4
        ],
        [
          3.4,
          3.6
        ],
        [
          2.4,
          3.6
        ]
      ],
      "label_anchor": [
        2.7,
        1.7
      ],
      "rotation": -90.0
    },
    {
      "id": "civic",
      "name": "CIVIC",
      "polygon": [
        [
          3.4,
          -0.4
        ],
        [
          7.4,
          -0.4
        ],
        [
          7.4,
          2.4
        ],
        [
          3.4,
          2.4
        ]
      ],
      "label_anchor": [
        6.6,
        -0.1
      ],
      "rotation": 0.0
    },
    {
      "id": "outskirts",
      "name": "OUTSKIRTS",
      "polygon": [
        [
          7.4,
          1.4
        ],
        [
          10.0,
          1.4
        ],
        [
          10.0,
          5.6
        ],
        [
          7.4,
          5.6
        ]
      ],
      "label_anchor": [
        8.7,
        5.2
      ],
      "rotation": 0.0
    },
    {
      "id": "jundland",
      "name": "JUNDLAND WASTES",
      "polygon": [
        [
          10.0,
          1.4
        ],
        [
          13.6,
          1.4
        ],
        [
          13.6,
          4.6
        ],
        [
          10.0,
          4.6
        ]
      ],
      "label_anchor": [
        11.8,
        1.7
      ],
      "rotation": 0.0
    },
    {
      "id": "dune_sea",
      "name": "DUNE SEA",
      "polygon": [
        [
          13.6,
          1.4
        ],
        [
          14.8,
          1.4
        ],
        [
          14.8,
          4.6
        ],
        [
          13.6,
          4.6
        ]
      ],
      "label_anchor": [
        14.2,
        4.0
      ],
      "rotation": -90.0
    }
  ],
  "rooms": [
    {
      "id": 1,
      "name": "Bay 94",
      "zone": "spaceport",
      "x": 3.9,
      "y": 6.4,
      "w": 0.9,
      "h": 0.9,
      "style": "dock",
      "symbol": "◎",
      "slug": "docking_bay_94_pit"
    },
    {
      "id": 0,
      "name": "Bay 94 Ent",
      "zone": "spaceport",
      "x": 4.7,
      "y": 6.4,
      "w": 0.4,
      "h": 0.4,
      "style": "dock",
      "symbol": "≡",
      "slug": "docking_bay_94_entrance"
    },
    {
      "id": 4,
      "name": "Bay 86",
      "zone": "spaceport",
      "x": 3.9,
      "y": 5.4,
      "w": 0.7,
      "h": 0.7,
      "style": "dock",
      "symbol": "◎",
      "slug": "docking_bay_86"
    },
    {
      "id": 25,
      "name": "Hotel",
      "zone": "spaceport",
      "x": 4.8,
      "y": 5.4,
      "w": 0.5,
      "h": 0.5,
      "style": "housing",
      "symbol": "⌂",
      "slug": "spaceport_hotel"
    },
    {
      "id": 17,
      "name": "Inn",
      "zone": "spaceport",
      "x": 3.9,
      "y": 4.6,
      "w": 0.5,
      "h": 0.5,
      "style": "housing",
      "symbol": "⌂",
      "slug": "mos_eisley_inn"
    },
    {
      "id": 31,
      "name": "Lucky Despot",
      "zone": "spaceport",
      "x": 3.0,
      "y": 6.4,
      "w": 0.7,
      "h": 0.7,
      "style": "housing",
      "symbol": "⌂",
      "slug": "lucky_despot_staircase"
    },
    {
      "id": 32,
      "name": "Star Chamber",
      "zone": "spaceport",
      "x": 3.0,
      "y": 5.5,
      "w": 0.5,
      "h": 0.5,
      "style": "cantina",
      "symbol": "Λ",
      "slug": "lucky_despot_star_chamber"
    },
    {
      "id": 5,
      "name": "Bay 87",
      "zone": "spaceport",
      "x": 6.3,
      "y": 6.4,
      "w": 0.7,
      "h": 0.7,
      "style": "dock",
      "symbol": "◎",
      "slug": "docking_bay_87"
    },
    {
      "id": 2,
      "name": "Customs",
      "zone": "spaceport",
      "x": 6.3,
      "y": 5.5,
      "w": 0.5,
      "h": 0.5,
      "style": "civic",
      "symbol": "§",
      "slug": "spaceport_customs_office"
    },
    {
      "id": 3,
      "name": "Speeders",
      "zone": "spaceport",
      "x": 6.3,
      "y": 4.7,
      "w": 0.5,
      "h": 0.5,
      "style": "vendor",
      "symbol": "⌬",
      "slug": "spaceport_speeders"
    },
    {
      "id": 34,
      "name": "Transport",
      "zone": "spaceport",
      "x": 7.0,
      "y": 5.5,
      "w": 0.5,
      "h": 0.5,
      "style": "civic",
      "symbol": "§",
      "slug": "transport_depot"
    },
    {
      "id": 38,
      "name": "M. Nadon",
      "zone": "spaceport",
      "x": 7.0,
      "y": 4.7,
      "w": 0.5,
      "h": 0.5,
      "style": "housing",
      "symbol": "⌂",
      "slug": "house_of_momaw_nadon"
    },
    {
      "id": 26,
      "name": "Tower",
      "zone": "spaceport",
      "x": 7.0,
      "y": 6.4,
      "w": 0.5,
      "h": 0.5,
      "style": "civic",
      "symbol": "T",
      "slug": "mos_eisley_control_tower"
    },
    {
      "id": 7,
      "name": "Spaceport Row",
      "zone": "spaceport",
      "x": 5.4,
      "y": 5.4,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·",
      "slug": "mos_eisley_spaceport_row"
    },
    {
      "id": 11,
      "name": "South End",
      "zone": "spaceport",
      "x": 5.4,
      "y": 6.4,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·",
      "slug": "mos_eisley_south_end"
    },
    {
      "id": 13,
      "name": "Cantina Bar",
      "zone": "cantina",
      "x": 2.8,
      "y": 2.9,
      "w": 0.7,
      "h": 0.5,
      "style": "cantina",
      "symbol": "Λ",
      "slug": "chalmuans_cantina_main_bar"
    },
    {
      "id": 14,
      "name": "Back Hall",
      "zone": "cantina",
      "x": 2.8,
      "y": 2.2,
      "w": 0.4,
      "h": 0.4,
      "style": "cantina",
      "symbol": "Λ",
      "slug": "chalmuans_cantina_back_hallway"
    },
    {
      "id": 12,
      "name": "Cantina Ent.",
      "zone": "cantina",
      "x": 3.5,
      "y": 2.9,
      "w": 0.45,
      "h": 0.45,
      "style": "cantina",
      "symbol": "Λ",
      "slug": "chalmuans_cantina_entrance"
    },
    {
      "id": 8,
      "name": "Market St.",
      "zone": "market",
      "x": 5.4,
      "y": 3.0,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·",
      "slug": "mos_eisley_market_district"
    },
    {
      "id": 29,
      "name": "Jawa Traders",
      "zone": "market",
      "x": 4.2,
      "y": 3.0,
      "w": 0.5,
      "h": 0.5,
      "style": "vendor",
      "symbol": "$",
      "slug": "jawa_traders"
    },
    {
      "id": 16,
      "name": "Gep's Grill",
      "zone": "market",
      "x": 4.7,
      "y": 3.0,
      "w": 0.45,
      "h": 0.45,
      "style": "market",
      "symbol": "#",
      "slug": "market_place_geps_grill"
    },
    {
      "id": 15,
      "name": "Lup's Store",
      "zone": "market",
      "x": 6.0,
      "y": 3.0,
      "w": 0.5,
      "h": 0.5,
      "style": "vendor",
      "symbol": "$",
      "slug": "lups_general_store"
    },
    {
      "id": 28,
      "name": "Souvenirs",
      "zone": "market",
      "x": 6.6,
      "y": 3.0,
      "w": 0.45,
      "h": 0.45,
      "style": "vendor",
      "symbol": "$",
      "slug": "heffs_souvenirs"
    },
    {
      "id": 33,
      "name": "Bank",
      "zone": "market",
      "x": 7.0,
      "y": 3.0,
      "w": 0.4,
      "h": 0.4,
      "style": "civic",
      "symbol": "§",
      "slug": "zygians_banking"
    },
    {
      "id": 27,
      "name": "Weapons",
      "zone": "market",
      "x": 6.0,
      "y": 2.5,
      "w": 0.5,
      "h": 0.4,
      "style": "vendor",
      "symbol": "$",
      "slug": "kaysons_weapon_shop"
    },
    {
      "id": 37,
      "name": "Dowager Q.",
      "zone": "market",
      "x": 5.4,
      "y": 2.5,
      "w": 0.5,
      "h": 0.4,
      "style": "landmark",
      "symbol": "※",
      "slug": "dowager_queen_corner"
    },
    {
      "id": 9,
      "name": "Gov. Qtr St.",
      "zone": "civic",
      "x": 5.4,
      "y": 1.6,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·",
      "slug": "mos_eisley_government_quarter"
    },
    {
      "id": 10,
      "name": "North End",
      "zone": "civic",
      "x": 5.4,
      "y": 0.4,
      "w": 0.45,
      "h": 0.45,
      "style": "street",
      "symbol": "·",
      "slug": "mos_eisley_north_end"
    },
    {
      "id": 21,
      "name": "Police",
      "zone": "civic",
      "x": 4.2,
      "y": 1.6,
      "w": 0.5,
      "h": 0.4,
      "style": "civic",
      "symbol": "§",
      "slug": "police_station_main"
    },
    {
      "id": 20,
      "name": "Prefect",
      "zone": "civic",
      "x": 3.7,
      "y": 1.0,
      "w": 0.5,
      "h": 0.4,
      "style": "civic",
      "symbol": "§",
      "slug": "regional_government_offices"
    },
    {
      "id": 22,
      "name": "Militia HQ",
      "zone": "civic",
      "x": 4.4,
      "y": 1.0,
      "w": 0.5,
      "h": 0.4,
      "style": "civic",
      "symbol": "§",
      "slug": "tatooine_militia_hq"
    },
    {
      "id": 18,
      "name": "Jabba's TH",
      "zone": "civic",
      "x": 6.4,
      "y": 1.6,
      "w": 0.5,
      "h": 0.4,
      "style": "hutt",
      "symbol": "H",
      "slug": "jabbas_townhouse_entrance"
    },
    {
      "id": 19,
      "name": "Audience",
      "zone": "civic",
      "x": 6.9,
      "y": 1.6,
      "w": 0.45,
      "h": 0.4,
      "style": "hutt",
      "symbol": "H",
      "slug": "jabbas_townhouse_audience"
    },
    {
      "id": 35,
      "name": "Clinic",
      "zone": "civic",
      "x": 6.4,
      "y": 1.0,
      "w": 0.45,
      "h": 0.4,
      "style": "medical",
      "symbol": "+",
      "slug": "cutting_edge_clinic"
    },
    {
      "id": 24,
      "name": "Power",
      "zone": "civic",
      "x": 6.9,
      "y": 1.0,
      "w": 0.45,
      "h": 0.4,
      "style": "vendor",
      "symbol": "⚡",
      "slug": "power_station"
    },
    {
      "id": 36,
      "name": "Dim-U",
      "zone": "civic",
      "x": 5.0,
      "y": 0.4,
      "w": 0.5,
      "h": 0.4,
      "style": "temple",
      "symbol": "T",
      "slug": "dimu_monastery_gate"
    },
    {
      "id": 23,
      "name": "Stables",
      "zone": "civic",
      "x": 6.0,
      "y": 0.4,
      "w": 0.5,
      "h": 0.4,
      "style": "vendor",
      "symbol": "~",
      "slug": "dewback_stables_garage"
    },
    {
      "id": 39,
      "name": "Notsub",
      "zone": "civic",
      "x": 6.6,
      "y": 0.4,
      "w": 0.45,
      "h": 0.4,
      "style": "vendor",
      "symbol": "$",
      "slug": "notsub_shipping_lobby"
    },
    {
      "id": 30,
      "name": "Dockside Cafe",
      "zone": "civic",
      "x": 3.7,
      "y": 0.4,
      "w": 0.5,
      "h": 0.4,
      "style": "cantina",
      "symbol": "Λ",
      "slug": "dockside_cafe"
    },
    {
      "id": 40,
      "name": "East Gate",
      "zone": "outskirts",
      "x": 7.7,
      "y": 3.0,
      "w": 0.45,
      "h": 0.45,
      "style": "gate",
      "symbol": "⨯",
      "slug": "outskirts_eastern_gate"
    },
    {
      "id": 41,
      "name": "Scavenger",
      "zone": "outskirts",
      "x": 8.3,
      "y": 2.5,
      "w": 0.5,
      "h": 0.4,
      "style": "vendor",
      "symbol": "$",
      "slug": "outskirts_scavenger_market"
    },
    {
      "id": 45,
      "name": "Sandcrawler",
      "zone": "outskirts",
      "x": 8.3,
      "y": 1.9,
      "w": 0.5,
      "h": 0.4,
      "style": "ruin",
      "symbol": "※",
      "slug": "outskirts_wrecked_sandcrawler"
    },
    {
      "id": 43,
      "name": "Track",
      "zone": "outskirts",
      "x": 9.0,
      "y": 2.0,
      "w": 0.5,
      "h": 0.4,
      "style": "vendor",
      "symbol": "~",
      "slug": "outskirts_speeder_track"
    },
    {
      "id": 42,
      "name": "Old Farm",
      "zone": "outskirts",
      "x": 8.3,
      "y": 3.7,
      "w": 0.5,
      "h": 0.4,
      "style": "ruin",
      "symbol": "※",
      "slug": "outskirts_abandoned_farm"
    },
    {
      "id": 46,
      "name": "Hermit Ridge",
      "zone": "outskirts",
      "x": 8.3,
      "y": 4.4,
      "w": 0.5,
      "h": 0.4,
      "style": "landmark",
      "symbol": "^",
      "slug": "outskirts_hermits_ridge"
    },
    {
      "id": 44,
      "name": "Checkpoint",
      "zone": "outskirts",
      "x": 9.4,
      "y": 3.0,
      "w": 0.45,
      "h": 0.45,
      "style": "gate",
      "symbol": "⨯",
      "slug": "outskirts_checkpoint"
    },
    {
      "id": 47,
      "name": "Junction",
      "zone": "outskirts",
      "x": 10.4,
      "y": 3.0,
      "w": 0.4,
      "h": 0.4,
      "style": "street",
      "symbol": "·",
      "slug": "outskirts_trail_junction"
    },
    {
      "id": 48,
      "name": "Canyon Mouth",
      "zone": "jundland",
      "x": 11.1,
      "y": 3.0,
      "w": 0.5,
      "h": 0.4,
      "style": "wilderness",
      "symbol": "^",
      "slug": "jundland_canyon_mouth"
    },
    {
      "id": 49,
      "name": "Beggar's Cyn.",
      "zone": "jundland",
      "x": 11.1,
      "y": 3.7,
      "w": 0.5,
      "h": 0.4,
      "style": "wilderness",
      "symbol": "^",
      "slug": "jundland_beggars_canyon"
    },
    {
      "id": 52,
      "name": "Hidden Cave",
      "zone": "jundland",
      "x": 11.1,
      "y": 2.3,
      "w": 0.4,
      "h": 0.35,
      "style": "hidden",
      "symbol": "?",
      "slug": "jundland_hidden_cave"
    },
    {
      "id": 50,
      "name": "Tusken Camp",
      "zone": "jundland",
      "x": 11.9,
      "y": 3.0,
      "w": 0.5,
      "h": 0.4,
      "style": "hostile",
      "symbol": "!",
      "slug": "jundland_tusken_overlook"
    },
    {
      "id": 51,
      "name": "Krayt Graveyd",
      "zone": "jundland",
      "x": 12.7,
      "y": 3.0,
      "w": 0.5,
      "h": 0.4,
      "style": "landmark",
      "symbol": "※",
      "slug": "jundland_krayt_graveyard"
    },
    {
      "id": 53,
      "name": "Dune Sea Edge",
      "zone": "dune_sea",
      "x": 14.2,
      "y": 3.0,
      "w": 0.4,
      "h": 0.4,
      "style": "wilderness",
      "symbol": "~",
      "slug": "jundland_dune_sea_edge"
    }
  ],
  "exits": [
    [
      0,
      1
    ],
    [
      0,
      7
    ],
    [
      2,
      7
    ],
    [
      3,
      7
    ],
    [
      4,
      7
    ],
    [
      5,
      7
    ],
    [
      7,
      8
    ],
    [
      8,
      9
    ],
    [
      9,
      10
    ],
    [
      7,
      11
    ],
    [
      12,
      8
    ],
    [
      12,
      13
    ],
    [
      13,
      14
    ],
    [
      15,
      8
    ],
    [
      16,
      8
    ],
    [
      17,
      7
    ],
    [
      18,
      8
    ],
    [
      18,
      19
    ],
    [
      20,
      9
    ],
    [
      21,
      9
    ],
    [
      22,
      9
    ],
    [
      23,
      22
    ],
    [
      24,
      9
    ],
    [
      25,
      7
    ],
    [
      26,
      7
    ],
    [
      27,
      8
    ],
    [
      28,
      8
    ],
    [
      29,
      8
    ],
    [
      30,
      10
    ],
    [
      31,
      11
    ],
    [
      31,
      32
    ],
    [
      33,
      8
    ],
    [
      34,
      11
    ],
    [
      35,
      9
    ],
    [
      36,
      10
    ],
    [
      37,
      8
    ],
    [
      38,
      11
    ],
    [
      39,
      10
    ],
    [
      40,
      8
    ],
    [
      41,
      40
    ],
    [
      42,
      40
    ],
    [
      43,
      41
    ],
    [
      44,
      40
    ],
    [
      45,
      41
    ],
    [
      46,
      42
    ],
    [
      47,
      44
    ],
    [
      48,
      47
    ],
    [
      49,
      48
    ],
    [
      50,
      48
    ],
    [
      51,
      50
    ],
    {
      "from": 52,
      "to": 48,
      "hidden": true
    },
    [
      53,
      51
    ]
  ],
  "exit_paths": {
    "11-7": {
      "kind": "street",
      "path": [
        [
          5.4,
          6.4
        ],
        [
          5.4,
          5.4
        ]
      ],
      "width": 0.3
    },
    "7-8": {
      "kind": "street",
      "path": [
        [
          5.4,
          5.4
        ],
        [
          5.4,
          4.4
        ],
        [
          5.4,
          3.4
        ],
        [
          5.4,
          3.0
        ]
      ],
      "width": 0.3
    },
    "8-9": {
      "kind": "street",
      "path": [
        [
          5.4,
          3.0
        ],
        [
          5.4,
          2.2
        ],
        [
          5.4,
          1.6
        ]
      ],
      "width": 0.3
    },
    "9-10": {
      "kind": "street",
      "path": [
        [
          5.4,
          1.6
        ],
        [
          5.4,
          1.0
        ],
        [
          5.4,
          0.4
        ]
      ],
      "width": 0.3
    },
    "12-8": {
      "kind": "alley",
      "path": [
        [
          3.5,
          2.9
        ],
        [
          4.0,
          2.9
        ],
        [
          4.5,
          2.95
        ],
        [
          5.0,
          3.0
        ],
        [
          5.4,
          3.0
        ]
      ],
      "width": 0.18
    },
    "40-8": {
      "kind": "road",
      "path": [
        [
          5.4,
          3.0
        ],
        [
          6.2,
          3.0
        ],
        [
          7.0,
          3.0
        ],
        [
          7.7,
          3.0
        ]
      ],
      "width": 0.22
    },
    "44-40": {
      "kind": "road",
      "path": [
        [
          7.7,
          3.0
        ],
        [
          8.5,
          3.0
        ],
        [
          9.4,
          3.0
        ]
      ],
      "width": 0.22
    },
    "47-44": {
      "kind": "road",
      "path": [
        [
          9.4,
          3.0
        ],
        [
          10.0,
          3.0
        ],
        [
          10.4,
          3.0
        ]
      ],
      "width": 0.22
    },
    "48-47": {
      "kind": "trail",
      "path": [
        [
          10.4,
          3.0
        ],
        [
          10.7,
          3.05
        ],
        [
          11.1,
          3.0
        ]
      ],
      "width": 0.1
    },
    "50-48": {
      "kind": "trail",
      "path": [
        [
          11.1,
          3.0
        ],
        [
          11.5,
          2.95
        ],
        [
          11.9,
          3.0
        ]
      ],
      "width": 0.1
    },
    "51-50": {
      "kind": "trail",
      "path": [
        [
          11.9,
          3.0
        ],
        [
          12.3,
          3.05
        ],
        [
          12.7,
          3.0
        ]
      ],
      "width": 0.1
    },
    "53-51": {
      "kind": "trail",
      "path": [
        [
          12.7,
          3.0
        ],
        [
          13.4,
          3.0
        ],
        [
          14.2,
          3.0
        ]
      ],
      "width": 0.08
    }
  },
  "labels": [
    {
      "text": "THE  WESTPORT",
      "kind": "street",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 9.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "path_id": "7-8"
    },
    {
      "text": "Cantina Lane",
      "kind": "street",
      "t": 0.32,
      "side": 0,
      "offset": 0.0,
      "size": 7.0,
      "weight": 300,
      "min_zoom": 1,
      "max_zoom": 2,
      "path_id": "12-8"
    },
    {
      "text": "OUTSKIRT  CAUSEWAY",
      "kind": "street",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 8.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "path_id": "44-40"
    },
    {
      "text": "JUNDLAND  TRAIL",
      "kind": "street",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 7.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "path_id": "50-48"
    },
    {
      "text": "Spaceport Row",
      "kind": "street",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 7.0,
      "weight": 300,
      "min_zoom": 1,
      "max_zoom": 1,
      "path_id": "11-7"
    },
    {
      "text": "to Anchorhead →",
      "kind": "flavor",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 6.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "pos": [
        9.5,
        2.2
      ],
      "rot": 0.0
    },
    {
      "text": "to the deep desert →",
      "kind": "flavor",
      "t": 0.5,
      "side": 0,
      "offset": 0.0,
      "size": 6.0,
      "weight": 400,
      "min_zoom": 1,
      "max_zoom": 2,
      "pos": [
        14.2,
        5.2
      ],
      "rot": 0.0
    }
  ],
  "landmarks": [
    {
      "id": "dowager",
      "icon": "wreck",
      "name": "Dowager Queen",
      "pos": [
        5.4,
        2.5
      ],
      "min_zoom": 2,
      "max_zoom": 3
    },
    {
      "id": "jabba_th",
      "icon": "hutt",
      "name": "Jabba's Townhouse",
      "pos": [
        6.4,
        1.6
      ],
      "min_zoom": 2,
      "max_zoom": 2
    },
    {
      "id": "chalmun",
      "icon": "cantina",
      "name": "Chalmun's Cantina",
      "pos": [
        2.8,
        2.9
      ],
      "min_zoom": 2,
      "max_zoom": 2
    },
    {
      "id": "bay94",
      "icon": "dock",
      "name": "Docking Bay 94",
      "pos": [
        3.9,
        6.4
      ],
      "min_zoom": 2,
      "max_zoom": 2
    },
    {
      "id": "despot",
      "icon": "ship",
      "name": "Lucky Despot",
      "pos": [
        3.0,
        6.4
      ],
      "min_zoom": 2,
      "max_zoom": 2
    },
    {
      "id": "kraytgrave",
      "icon": "bones",
      "name": "Krayt Graveyard",
      "pos": [
        12.7,
        3.0
      ],
      "min_zoom": 2,
      "max_zoom": 3
    },
    {
      "id": "jabba_p",
      "icon": "palace",
      "name": "Jabba's Palace ↗",
      "pos": [
        14.5,
        5.5
      ],
      "min_zoom": 2,
      "max_zoom": 3
    },
    {
      "id": "sarlacc",
      "icon": "sarlacc",
      "name": "The Sarlacc ↗",
      "pos": [
        14.5,
        6.4
      ],
      "min_zoom": 2,
      "max_zoom": 3
    },
    {
      "id": "beacon",
      "icon": "beacon",
      "name": "Hyperspace Beacon",
      "pos": [
        5.4,
        6.9
      ],
      "min_zoom": 2,
      "max_zoom": 3
    }
  ],
  "player": {
    "room_id": 1,
    "x": 3.9,
    "y": 6.4
  },
  "contacts": []
};
