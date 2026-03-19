# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalMixin(models.AbstractModel):
    """Mixin to add approval workflow capability to any model.
    
    Usage:
        1. Inherit this mixin in your model
        2. Create an approval workflow (sm.approval.config) for your model
        3. Use the provided methods and buttons
    
    Example:
        class SaleOrder(models.Model):
            _inherit = ["sale.order", "sm.approval.mixin"]
            _approval_model = "sale.order"
    """
    
    _name = "sm.approval.mixin"
    _description = "SM Approval Mixin"
    _approval_model = None  # Override in inheriting model

    # Approval Fields
    sm_approval_request_id = fields.Many2one(
        comodel_name="sm.approval.request",
        string="Approval Request",
        copy=False,
    )
    sm_approval_state = fields.Selection(
        related="sm_approval_request_id.state",
        string="Approval Status",
        store=True,
    )
    sm_needs_approval = fields.Boolean(
        compute="_compute_sm_needs_approval",
        string="Needs Approval",
    )
    sm_can_approve = fields.Boolean(
        compute="_compute_sm_can_approve",
        string="Can Approve",
    )
    sm_current_stage = fields.Char(
        related="sm_approval_request_id.current_stage_id.name",
        string="Current Approval Stage",
    )
    sm_approval_progress = fields.Float(
        compute="_compute_sm_approval_progress",
        string="Approval Progress",
    )

    @api.depends_context("uid")
    def _compute_sm_needs_approval(self):
        """Check if record needs approval workflow."""
        for record in self:
            config = self.env["sm.approval.config"].sudo().get_matching_config(record)
            record.sm_needs_approval = bool(config)

    @api.depends("sm_approval_request_id", "sm_approval_request_id.current_approvers")
    @api.depends_context("uid")
    def _compute_sm_can_approve(self):
        """Check if current user can approve this record."""
        for record in self:
            if not record.sm_approval_request_id:
                record.sm_can_approve = False
            elif record.sm_approval_request_id.state != "pending":
                record.sm_can_approve = False
            else:
                record.sm_can_approve = self.env.user in record.sm_approval_request_id.current_approvers

    @api.depends("sm_approval_request_id.current_stage_sequence")
    def _compute_sm_approval_progress(self):
        """Calculate approval progress percentage."""
        for record in self:
            if not record.sm_approval_request_id:
                record.sm_approval_progress = 0.0
            elif record.sm_approval_state == "approved":
                record.sm_approval_progress = 100.0
            elif record.sm_approval_request_id.config_id:
                total_stages = len(record.sm_approval_request_id.config_id.stage_ids)
                if total_stages and record.sm_approval_request_id.current_stage_id:
                    stages = list(
                        record.sm_approval_request_id.config_id.stage_ids.sorted("sequence")
                    )
                    try:
                        current_idx = stages.index(record.sm_approval_request_id.current_stage_id)
                    except ValueError:
                        current_idx = 0
                    record.sm_approval_progress = (current_idx / total_stages) * 100
                else:
                    record.sm_approval_progress = 0.0
            else:
                record.sm_approval_progress = 0.0

    def action_sm_request_approval(self):
        """Create approval request and submit."""
        self.ensure_one()
        
        model_name = self._approval_model or self._name
        
        # Check if there's already an active/pending approval request
        if self.sm_approval_request_id and self.sm_approval_request_id.state in ('draft', 'pending'):
            raise UserError(_("An approval request already exists for this document. Please wait for it to be processed."))
        
        # Check if there's an existing pending request for this record (safety check)
        existing_request = self.env["sm.approval.request"].sudo().search([
            ("res_model", "=", model_name),
            ("res_id", "=", self.id),
            ("state", "in", ["draft", "pending"]),
        ], limit=1)
        
        if existing_request:
            # Link to existing request if not linked
            if not self.sm_approval_request_id:
                self.sm_approval_request_id = existing_request.id
            raise UserError(_("An approval request already exists for this document. Please wait for it to be processed."))
        
        # Find matching workflow using centralized method
        config = self.env["sm.approval.config"].sudo().get_matching_config(self)
        
        if not config:
            raise UserError(_("No approval workflow configured for this document type."))
        
        # Create approval request
        request = self.env["sm.approval.request"].create({
            "config_id": config.id,
            "res_model": model_name,
            "res_id": self.id,
            "requester_id": self.env.user.id,
            "company_id": self.company_id.id if hasattr(self, "company_id") else False,
        })
        
        self.sm_approval_request_id = request.id
        
        # Submit for approval
        request.action_submit()
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Approval request submitted successfully."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_sm_approve(self):
        """Approve current stage."""
        self.ensure_one()
        
        if not self.sm_approval_request_id:
            raise UserError(_("No approval request found."))
        
        return self.sm_approval_request_id.action_approve()

    def action_sm_reject(self):
        """Reject request - opens wizard for reason."""
        self.ensure_one()
        
        if not self.sm_approval_request_id:
            raise UserError(_("No approval request found."))
        
        return {
            "name": _("Reject Request"),
            "type": "ir.actions.act_window",
            "res_model": "sm.approval.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_request_id": self.sm_approval_request_id.id,
            },
        }

    def action_sm_cancel_approval(self):
        """Cancel the approval request."""
        self.ensure_one()
        
        if not self.sm_approval_request_id:
            raise UserError(_("No approval request found."))
        
        return self.sm_approval_request_id.action_cancel()

    def action_sm_delegate(self):
        """Delegate current approval to another user."""
        self.ensure_one()
        
        if not self.sm_approval_request_id:
            raise UserError(_("No approval request found."))
        
        return self.sm_approval_request_id.action_delegate()

    def action_sm_view_approval(self):
        """View approval request details."""
        self.ensure_one()
        
        if not self.sm_approval_request_id:
            raise UserError(_("No approval request found."))
        
        return {
            "type": "ir.actions.act_window",
            "res_model": "sm.approval.request",
            "res_id": self.sm_approval_request_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_sm_view_approval_history(self):
        """View approval history."""
        self.ensure_one()
        
        if not self.sm_approval_request_id:
            raise UserError(_("No approval request found."))
        
        return {
            "type": "ir.actions.act_window",
            "name": _("Approval History"),
            "res_model": "sm.approval.history",
            "view_mode": "tree,form",
            "domain": [("request_id", "=", self.sm_approval_request_id.id)],
            "context": {"create": False, "edit": False},
        }

    def _on_approval_complete(self, request):
        """Callback when approval is completed.
        
        Override this method in your model to add custom logic
        when the document is fully approved.
        
        Args:
            request: sm.approval.request record
        """
        pass  # Override in inheriting model

    def _on_approval_rejected(self, request):
        """Callback when approval is rejected.
        
        Override this method in your model to add custom logic
        when the document approval is rejected.
        
        Args:
            request: sm.approval.request record
        """
        pass  # Override in inheriting model
