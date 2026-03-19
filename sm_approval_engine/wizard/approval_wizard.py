# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ApprovalRejectWizard(models.TransientModel):
    """Wizard for rejecting approval requests with reason."""
    
    _name = "sm.approval.reject.wizard"
    _description = "Reject Approval Wizard"

    request_id = fields.Many2one(
        comodel_name="sm.approval.request",
        string="Approval Request",
        required=True,
    )
    reason = fields.Text(
        string="Rejection Reason",
        required=True,
    )

    def action_reject(self):
        """Execute rejection with reason."""
        self.ensure_one()
        
        if not self.reason:
            raise UserError(_("Please provide a rejection reason."))
        
        return self.request_id.action_reject(reason=self.reason)


class ApprovalDelegateWizard(models.TransientModel):
    """Wizard for delegating approval to another user."""
    
    _name = "sm.approval.delegate.wizard"
    _description = "Delegate Approval Wizard"

    request_id = fields.Many2one(
        comodel_name="sm.approval.request",
        string="Approval Request",
        required=True,
    )
    delegate_to_id = fields.Many2one(
        comodel_name="res.users",
        string="Delegate To",
        required=True,
        domain="[('share', '=', False)]",
    )
    comment = fields.Text(
        string="Comment",
    )

    def action_delegate(self):
        """Execute delegation."""
        self.ensure_one()
        
        # Check if current user can delegate
        if self.env.user not in self.request_id.current_approvers:
            raise UserError(_("You are not authorized to delegate this approval."))
        
        if not self.request_id.current_stage_id.allow_delegation:
            raise UserError(_("Delegation is not allowed at this stage."))
        
        # Create delegation history
        self.env["sm.approval.history"].create({
            "request_id": self.request_id.id,
            "stage_id": self.request_id.current_stage_id.id,
            "action": "delegate",
            "user_id": self.env.user.id,
            "comment": _("Delegated to %s. %s") % (
                self.delegate_to_id.name,
                self.comment or ""
            ),
        })
        
        # Store delegation on the request (temporary override for current stage)
        # Do NOT modify the stage itself, as it would permanently change the workflow
        self.request_id.write({"delegated_approver_id": self.delegate_to_id.id})
        
        # Recompute current approvers
        self.request_id._compute_current_approvers()
        
        # Notify delegate
        self.request_id.activity_schedule(
            "mail.mail_activity_data_todo",
            user_id=self.delegate_to_id.id,
            note=_("Approval delegated to you by %s: %s") % (
                self.env.user.name,
                self.request_id.display_name
            ),
        )
        
        # Post message on request
        self.request_id.message_post(
            body=_("🔄 Approval delegated from %s to %s.") % (
                self.env.user.name,
                self.delegate_to_id.name,
            ),
            message_type="notification",
        )
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("Approval delegated to %s.") % self.delegate_to_id.name,
                "type": "success",
                "sticky": False,
            },
        }
