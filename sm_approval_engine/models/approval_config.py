# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


class ApprovalConfig(models.Model):
    """Configuration for approval workflows per model."""
    
    _name = "sm.approval.config"
    _description = "SM Approval Configuration"
    _order = "sequence, id"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Workflow Name",
        required=True,
        tracking=True,
    )
    active = fields.Boolean(
        default=True,
        tracking=True,
    )
    sequence = fields.Integer(
        default=10,
        help="Lower sequence = higher priority when multiple configs match",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Target Model",
        required=True,
        ondelete="cascade",
        domain=[("transient", "=", False)],
        tracking=True,
    )
    model_name = fields.Char(
        related="model_id.model",
        store=True,
        index=True,
    )
    domain = fields.Char(
        string="Filter Domain",
        default="[]",
        help="Optional domain to filter which records use this workflow. "
             "Example: [('amount_total', '>=', 10000)]",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    stage_ids = fields.One2many(
        comodel_name="sm.approval.stage",
        inverse_name="config_id",
        string="Approval Stages",
        copy=True,
    )
    stage_count = fields.Integer(
        compute="_compute_stage_count",
    )
    request_count = fields.Integer(
        compute="_compute_request_count",
    )
    
    # Workflow Settings
    approval_mode = fields.Selection(
        selection=[
            ("sequential", "Sequential (one stage at a time)"),
            ("parallel", "Parallel (all stages at once)"),
        ],
        default="sequential",
        required=True,
        tracking=True,
    )
    allow_self_approval = fields.Boolean(
        string="Allow Self Approval",
        default=False,
        help="If enabled, requester can approve their own requests",
    )
    
    # Notification Settings
    notify_requester_on_approve = fields.Boolean(
        string="Notify Requester on Approve",
        default=True,
    )
    notify_requester_on_reject = fields.Boolean(
        string="Notify Requester on Reject",
        default=True,
    )
    escalation_enabled = fields.Boolean(
        string="Enable Escalation",
        default=False,
        help="Automatically escalate overdue approval requests",
    )
    escalation_hours = fields.Integer(
        string="Escalation After (Hours)",
        default=24,
        help="Hours before overdue requests are escalated. 0 = no escalation.",
    )
    
    # Callbacks
    on_approve_callback = fields.Char(
        string="On Approve Callback",
        help="Method name to call on the source document when fully approved. E.g., 'action_confirm'",
    )
    on_reject_callback = fields.Char(
        string="On Reject Callback",
        help="Method name to call on the source document when rejected. E.g., 'action_cancel'",
    )

    @api.depends("stage_ids")
    def _compute_stage_count(self):
        for config in self:
            config.stage_count = len(config.stage_ids)

    def _compute_request_count(self):
        Request = self.env["sm.approval.request"]
        for config in self:
            config.request_count = Request.search_count([
                ("config_id", "=", config.id)
            ])

    @api.constrains("domain")
    def _check_domain(self):
        for config in self:
            if config.domain:
                try:
                    domain = safe_eval(config.domain)
                    if not isinstance(domain, list):
                        raise ValidationError(
                            _("Domain must be a valid list. Example: [('field', '=', 'value')]")
                        )
                except Exception as e:
                    raise ValidationError(
                        _("Invalid domain syntax: %s") % str(e)
                    )

    def action_view_requests(self):
        """Open requests linked to this config."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Requests"),
            "res_model": "sm.approval.request",
            "view_mode": "list,kanban,form",
            "domain": [("config_id", "=", self.id)],
            "context": {"default_config_id": self.id},
        }

    def action_view_stages(self):
        """Open stages for this config."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval Stages"),
            "res_model": "sm.approval.stage",
            "view_mode": "tree,form",
            "domain": [("config_id", "=", self.id)],
            "context": {"default_config_id": self.id},
        }

    def get_matching_config(self, record):
        """Find the first matching config for a record.
        
        Args:
            record: The record to match against
            
        Returns:
            sm.approval.config record or empty recordset
        """
        configs = self.search([
            ("model_name", "=", record._name),
            ("active", "=", True),
            "|",
            ("company_id", "=", False),
            ("company_id", "=", record.company_id.id if hasattr(record, "company_id") else self.env.company.id),
        ], order="sequence, id")
        
        for config in configs:
            if config.domain and config.domain != "[]":
                try:
                    domain = safe_eval(config.domain)
                    if record.filtered_domain(domain):
                        return config
                except Exception as e:
                    _logger.warning(
                        "Config %s has invalid domain %s: %s",
                        config.name, config.domain, e
                    )
                    continue
            else:
                return config
        
        return self.browse()
