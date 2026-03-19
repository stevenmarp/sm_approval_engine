# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp
{
    "name": "Approval Engine",
    "version": "18.0.1.0.0",
    "summary": "Universal multi-stage approval workflow engine for any Odoo model",
    "description": """
Approval Engine - Universal Approval Workflow
=================================================

A powerful, flexible approval engine that can be integrated with any Odoo model.
Built with modern OWL components for a seamless user experience.

Key Features
------------
* **Universal Integration** - Works with any Odoo model via simple mixin
* **Multi-Stage Workflows** - Configure unlimited approval stages
* **Flexible Approvers** - User, Group, or Dynamic field-based approvers
* **Modern Dashboard** - OWL-based dashboard with real-time stats
* **Parallel & Sequential** - Support both approval modes
* **Delegation** - Approvers can delegate to others
* **Escalation** - Auto-escalate overdue requests
* **Complete Audit Trail** - Track every action with timestamps
* **Mobile Friendly** - Responsive design for mobile approval

Author: Steven Marp
Website: https://apps.odoo.com/apps/browse?repo_maintainer_id=512936
    """,
    "author": "Steven Marp",
    "website": "https://apps.odoo.com/apps/browse?repo_maintainer_id=512936",
    "category": "Productivity",
    "license": "LGPL-3",
    "depends": ["base", "mail", "hr", "sale"],
    "data": [
        # Security
        "security/approval_security.xml",
        "security/ir.model.access.csv",
        # Data
        "data/approval_cron.xml",
        # Views
        "views/approval_config_views.xml",
        "views/approval_request_views.xml",
        "views/sale_order_views.xml",
        "views/menu.xml",
        # Wizard
        "wizard/approval_wizard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sm_approval_engine/static/src/js/approval_dashboard.js",
            "sm_approval_engine/static/src/xml/approval_dashboard.xml",
            "sm_approval_engine/static/src/scss/approval_dashboard.scss",
        ],
    },
    "images": ["static/description/banner.gif"],
    "installable": True,
    "application": True,
    "auto_install": False,
    "price": 379.00,
    "currency": "USD",
}
