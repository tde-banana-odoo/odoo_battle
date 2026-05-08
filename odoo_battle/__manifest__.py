{
    'name': 'Mass Battle',
    'version': '1.0',
    'category': 'JdR',
    'complexity': 'easy',
    'description': """Mass Battle""",
    'depends': [
        'mail',
    ],
    'data': [
        'security/ir.access.csv',
        'wizard/battle_solver_views.xml',
        'views/battle_faction_views.xml',
        'views/battle_outcome_views.xml',
        'views/battle_location_views.xml',
        'views/battle_trait_views.xml',
        'views/battle_unit_template_views.xml',
        'views/battle_unit_views.xml',
        'views/battle_menus.xml',
        'data/battle_trait_data.xml',
        'data/battle_location_data.xml',
        'data/battle_faction_data.xml',
        'data/battle_outcome_data.xml',
        'data/battle.unit.template.csv',
        'data/battle.unit.csv',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo_battle/static/src/**/*',
        ],
    },
    'author': "Thibault Delavallee",
    'license': 'LGPL-3',
}
