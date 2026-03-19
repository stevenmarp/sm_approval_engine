# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class ApprovalRequest(models.Model):
    """Tracks individual approval request workflow."""
    
    _name = "sm.approval.request"
    _description = "SM Approval Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"
    _rec_name = "display_name"

    # Core Fields
    config_id = fields.Many2one(
        comodel_name="sm.approval.config",
        string="Workflow",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    res_model = fields.Char(
        string="Model",
        required=True,
        index=True,
    )
    res_id = fields.Integer(
        string="Resource ID",
        required=True,
        index=True,
    )
    
    # State
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    
    # Stage Tracking
    current_stage_id = fields.Many2one(
        comodel_name="sm.approval.stage",
        string="Current Stage",
        tracking=True,
    )
    current_stage_sequence = fields.Integer(
        related="current_stage_id.sequence",
        store=True,
    )
    
    # Participants
    requester_id = fields.Many2one(
        comodel_name="res.users",
        string="Requester",
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    current_approvers = fields.Many2many(
        comodel_name="res.users",
        string="Current Approvers",
        compute="_compute_current_approvers",
        store=True,
    )
    
    # Tracking
    request_date = fields.Datetime(
        string="Request Date",
        default=fields.Datetime.now,
    )
    completion_date = fields.Datetime(
        string="Completion Date",
    )
    rejection_reason = fields.Text(
        string="Rejection Reason",
    )
    
    # Company
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    
    # History Lines
    history_ids = fields.One2many(
        comodel_name="sm.approval.history",
        inverse_name="request_id",
        string="Approval History",
    )
    
    # Delegation support
    delegated_approver_id = fields.Many2one(
        comodel_name="res.users",
        string="Delegated Approver",
        help="User who was delegated to approve the current stage",
    )
    
    # Related Document
    source_document = fields.Reference(
        selection="_selection_source_document",
        string="Source Document",
        compute="_compute_source_document",
    )
    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
    )
    
    @api.model
    def _selection_source_document(self):
        """Dynamic selection for source document reference."""
        # Use sudo to allow regular users to access ir.model
        models = self.env["ir.model"].sudo().search([])
        return [(m.model, m.name) for m in models]

    @api.depends("res_model", "res_id", "config_id")
    def _compute_display_name(self):
        for request in self:
            if request.res_model and request.res_id:
                try:
                    record = self.env[request.res_model].sudo().browse(request.res_id)
                    if record.exists():
                        request.display_name = f"{request.config_id.name}: {record.display_name}"
                    else:
                        request.display_name = f"{request.config_id.name}: #{request.res_id}"
                except Exception:
                    request.display_name = f"{request.config_id.name}: #{request.res_id}"
            else:
                request.display_name = _("New Request")

    @api.depends("res_model", "res_id")
    def _compute_source_document(self):
        for request in self:
            if request.res_model and request.res_id:
                request.source_document = f"{request.res_model},{request.res_id}"
            else:
                request.source_document = False

    @api.depends("current_stage_id", "delegated_approver_id")
    def _compute_current_approvers(self):
        for request in self:
            if request.delegated_approver_id:
                # Delegation overrides the stage approver
                request.current_approvers = request.delegated_approver_id
            elif request.current_stage_id and request.res_model and request.res_id:
                try:
                    source_record = self.env[request.res_model].sudo().browse(request.res_id)
                    if source_record.exists():
                        request.current_approvers = request.current_stage_id.get_approvers(source_record)
                    else:
                        request.current_approvers = False
                except Exception:
                    request.current_approvers = False
            else:
                request.current_approvers = False

    def action_submit(self):
        """Submit request for approval - move to first stage."""
        for request in self:
            if request.state != "draft":
                raise UserError(_("Only draft requests can be submitted."))
            
            # Get first stage
            first_stage = request.config_id.stage_ids.sorted("sequence")[:1]
            if not first_stage:
                raise UserError(_("No approval stages defined in workflow '%s'.") % request.config_id.name)
            
            request.write({
                "state": "pending",
                "current_stage_id": first_stage.id,
                "request_date": fields.Datetime.now(),
            })
            
            # Create history entry
            self.env["sm.approval.history"].create({
                "request_id": request.id,
                "stage_id": first_stage.id,
                "action": "submit",
                "user_id": self.env.user.id,
            })
            
            # Send notifications
            request._send_approval_notifications()
        
        return True

    def action_approve(self):
        """Approve current stage."""
        for request in self:
            if request.state != "pending":
                raise UserError(_("Only pending requests can be approved."))
            
            if self.env.user not in request.current_approvers:
                raise UserError(_("You are not authorized to approve this request."))
            
            # Check self-approval
            if not request.config_id.allow_self_approval and self.env.user == request.requester_id:
                raise UserError(_("You cannot approve your own request. Self-approval is not allowed for this workflow."))
            
            # Check if all group members need to approve (for group type)
            if (request.current_stage_id.approver_type == "group" 
                    and request.current_stage_id.require_all_group_members
                    and not request.delegated_approver_id):
                # Check if all group members have approved
                approved_users = request.history_ids.filtered(
                    lambda h: h.stage_id == request.current_stage_id and h.action == "approve"
                ).mapped("user_id")
                
                remaining = request.current_approvers - approved_users - self.env.user
                if remaining:
                    # Record this approval but don't advance
                    self.env["sm.approval.history"].create({
                        "request_id": request.id,
                        "stage_id": request.current_stage_id.id,
                        "action": "approve",
                        "user_id": self.env.user.id,
                    })
                    request.message_post(
                        body=_("Approved by %s. Waiting for: %s") % (
                            self.env.user.name,
                            ", ".join(remaining.mapped("name"))
                        )
                    )
                    continue
            
            # Create history entry
            self.env["sm.approval.history"].create({
                "request_id": request.id,
                "stage_id": request.current_stage_id.id,
                "action": "approve",
                "user_id": self.env.user.id,
            })
            
            # Clear delegation when advancing
            if request.delegated_approver_id:
                request.delegated_approver_id = False
            
            # Move to next stage or complete
            request._advance_to_next_stage()
        
        return True

    def action_reject(self, reason=None):
        """Reject the request."""
        for request in self:
            if request.state != "pending":
                raise UserError(_("Only pending requests can be rejected."))
            
            if self.env.user not in request.current_approvers:
                raise UserError(_("You are not authorized to reject this request."))
            
            # Check if rejection is allowed at this stage
            if not request.current_stage_id.can_reject:
                raise UserError(_("Rejection is not allowed at stage '%s'.") % request.current_stage_id.name)
            
            if request.current_stage_id.rejection_reason_required and not reason:
                return {
                    "name": _("Rejection Reason"),
                    "type": "ir.actions.act_window",
                    "res_model": "sm.approval.reject.wizard",
                    "view_mode": "form",
                    "target": "new",
                    "context": {"default_request_id": request.id},
                }
            
            request.write({
                "state": "rejected",
                "rejection_reason": reason,
                "completion_date": fields.Datetime.now(),
            })
            
            # Create history entry
            self.env["sm.approval.history"].create({
                "request_id": request.id,
                "stage_id": request.current_stage_id.id,
                "action": "reject",
                "user_id": self.env.user.id,
                "comment": reason,
            })
            
            # Notify requester
            request._notify_rejection()
            
            # Execute rejection callback
            request._execute_rejection_callback()
        
        return True

    def action_cancel(self):
        """Cancel the request."""
        for request in self:
            if request.state in ("approved", "cancelled"):
                raise UserError(_("Cannot cancel an already completed or cancelled request."))
            
            request.write({
                "state": "cancelled",
                "completion_date": fields.Datetime.now(),
            })
            
            # Create history entry
            self.env["sm.approval.history"].create({
                "request_id": request.id,
                "stage_id": request.current_stage_id.id if request.current_stage_id else False,
                "action": "cancel",
                "user_id": self.env.user.id,
            })
        
        return True

    def action_reset_to_draft(self):
        """Reset to draft (only by requester or admin)."""
        for request in self:
            if request.state not in ("rejected", "cancelled"):
                raise UserError(_("Only rejected or cancelled requests can be reset."))
            
            if self.env.user != request.requester_id and not self.env.user.has_group("sm_approval_engine.group_approval_manager"):
                raise UserError(_("Only the requester or approval manager can reset this request."))
            
            request.write({
                "state": "draft",
                "current_stage_id": False,
                "rejection_reason": False,
                "completion_date": False,
            })
        
        return True

    def _advance_to_next_stage(self):
        """Move to the next stage or complete the workflow."""
        self.ensure_one()
        
        if self.config_id.approval_mode == "parallel":
            # Parallel mode: check if ALL stages have been approved
            stages = self.config_id.stage_ids.sorted("sequence")
            approved_stage_ids = self.history_ids.filtered(
                lambda h: h.action == "approve"
            ).mapped("stage_id").ids
            
            all_approved = all(stage.id in approved_stage_ids for stage in stages)
            
            if all_approved:
                self.write({
                    "state": "approved",
                    "completion_date": fields.Datetime.now(),
                })
                self._execute_approval_callback()
            else:
                # Find next unapproved stage
                for stage in stages:
                    if stage.id not in approved_stage_ids:
                        self.write({"current_stage_id": stage.id})
                        self._send_approval_notifications()
                        break
        else:
            # Sequential mode
            stages = self.config_id.stage_ids.sorted("sequence")
            stage_list = list(stages)
            
            try:
                current_idx = stage_list.index(self.current_stage_id)
            except ValueError:
                current_idx = -1
            
            if current_idx < len(stage_list) - 1:
                # Move to next stage
                next_stage = stage_list[current_idx + 1]
                self.write({"current_stage_id": next_stage.id})
                self._send_approval_notifications()
            else:
                # All stages completed
                self.write({
                    "state": "approved",
                    "completion_date": fields.Datetime.now(),
                })
                self._execute_approval_callback()

    def _send_approval_notifications(self):
        """Send notifications to current approvers."""
        self.ensure_one()
        
        for approver in self.current_approvers:
            # Email notification via mail.activity
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=approver.id,
                note=_("Please review and approve: %s") % self.display_name,
            )

    def _notify_rejection(self):
        """Notify requester about rejection."""
        self.ensure_one()
        
        if not self.config_id.notify_requester_on_reject:
            return
        
        self.activity_schedule(
            "mail.mail_activity_data_warning",
            user_id=self.requester_id.id,
            note=_("Your request '%s' has been rejected. Reason: %s") % (
                self.display_name,
                self.rejection_reason or _("No reason provided")
            ),
        )

    def _execute_approval_callback(self):
        """Execute callback method on source document when fully approved."""
        self.ensure_one()
        
        # Notify requester if configured
        if self.config_id.notify_requester_on_approve:
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=self.requester_id.id,
                note=_("✅ Your request '%s' has been fully approved!") % self.display_name,
            )
        
        if not self.res_model or not self.res_id:
            return
        
        try:
            record = self.env[self.res_model].browse(self.res_id)
            if record.exists():
                # Call standard callback method
                if hasattr(record, "_on_approval_complete"):
                    record._on_approval_complete(self)
                
                # Call custom callback from config
                if self.config_id.on_approve_callback:
                    method = getattr(record, self.config_id.on_approve_callback, None)
                    if callable(method):
                        method()
        except Exception as e:
            self.message_post(
                body=_("Error executing approval callback: %s") % str(e),
                message_type="notification",
            )

    def _execute_rejection_callback(self):
        """Execute callback method on source document when rejected."""
        self.ensure_one()
        
        if not self.res_model or not self.res_id:
            return
        
        try:
            record = self.env[self.res_model].browse(self.res_id)
            if record.exists():
                # Call standard rejection callback method
                if hasattr(record, "_on_approval_rejected"):
                    record._on_approval_rejected(self)
                
                # Call custom callback from config
                if self.config_id.on_reject_callback:
                    method = getattr(record, self.config_id.on_reject_callback, None)
                    if callable(method):
                        method()
        except Exception as e:
            self.message_post(
                body=_("Error executing rejection callback: %s") % str(e),
                message_type="notification",
            )

    @api.model
    def _cron_escalate_overdue(self):
        """Cron job: Escalate overdue approval requests."""
        overdue_requests = self.search([
            ("state", "=", "pending"),
            ("config_id.escalation_enabled", "=", True),
        ])
        
        now = fields.Datetime.now()
        
        for request in overdue_requests:
            if not request.config_id.escalation_hours:
                continue
            
            # Calculate the deadline based on when request entered current stage
            last_action = request.history_ids.sorted("create_date", reverse=True)[:1]
            if not last_action:
                continue
            
            deadline = last_action.create_date + timedelta(hours=request.config_id.escalation_hours)
            
            if now > deadline:
                # Escalate: notify escalation contact or manager
                escalation_user = request.current_stage_id.escalation_user_id
                if escalation_user:
                    request.activity_schedule(
                        "mail.mail_activity_data_warning",
                        user_id=escalation_user.id,
                        note=_("⚠️ OVERDUE: Approval request '%s' has exceeded the deadline of %d hours. "
                               "Current stage: %s") % (
                            request.display_name,
                            request.config_id.escalation_hours,
                            request.current_stage_id.name,
                        ),
                    )
                    request.message_post(
                        body=_("⚠️ Escalated to %s - request overdue by %d hours.") % (
                            escalation_user.name,
                            request.config_id.escalation_hours,
                        ),
                        message_type="notification",
                    )
                    _logger.info(
                        "Escalated approval request %s (ID: %s) to %s",
                        request.display_name, request.id, escalation_user.name
                    )

    def action_view_source_document(self):
        """Open the source document."""
        self.ensure_one()
        
        if not self.res_model or not self.res_id:
            raise UserError(_("No source document linked."))
        
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    def action_delegate(self):
        """Open delegation wizard."""
        self.ensure_one()
        
        if self.state != "pending":
            raise UserError(_("Only pending requests can be delegated."))
        
        if self.env.user not in self.current_approvers:
            raise UserError(_("You are not authorized to delegate this approval."))
        
        if not self.current_stage_id.allow_delegation:
            raise UserError(_("Delegation is not allowed at stage '%s'.") % self.current_stage_id.name)
        
        return {
            "name": _("Delegate Approval"),
            "type": "ir.actions.act_window",
            "res_model": "sm.approval.delegate.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_request_id": self.id,
            },
        }

    @api.model
    def get_dashboard_stats(self):
        """Get dashboard statistics for current user."""
        user_id = self.env.user.id
        
        # Use sudo to ensure we can count all records
        Request = self.env["sm.approval.request"].sudo()
        
        pending = Request.search_count([("state", "=", "pending")])
        approved = Request.search_count([("state", "=", "approved")])
        rejected = Request.search_count([("state", "=", "rejected")])
        
        # My pending - where current user is in approvers
        my_pending = Request.search_count([
            ("current_approvers", "in", [user_id]),
            ("state", "=", "pending"),
        ])
        
        # Recent pending requests
        recent_requests = Request.search_read(
            [("state", "=", "pending")],
            ["display_name", "config_id", "requester_id", "current_stage_id", "request_date"],
            limit=5,
            order="request_date desc",
        )
        
        # My pending approvals
        my_approvals = Request.search_read(
            [("current_approvers", "in", [user_id]), ("state", "=", "pending")],
            ["display_name", "config_id", "requester_id", "current_stage_id"],
            limit=5,
            order="request_date desc",
        )
        
        return {
            "stats": {
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
                "myPending": my_pending,
            },
            "recentRequests": recent_requests,
            "myApprovals": my_approvals,
        }


class ApprovalHistory(models.Model):
    """Tracks approval actions history."""
    
    _name = "sm.approval.history"
    _description = "SM Approval History"
    _order = "create_date desc"

    request_id = fields.Many2one(
        comodel_name="sm.approval.request",
        string="Request",
        required=True,
        ondelete="cascade",
    )
    stage_id = fields.Many2one(
        comodel_name="sm.approval.stage",
        string="Stage",
    )
    action = fields.Selection(
        selection=[
            ("submit", "Submitted"),
            ("approve", "Approved"),
            ("reject", "Rejected"),
            ("cancel", "Cancelled"),
            ("delegate", "Delegated"),
        ],
        string="Action",
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        required=True,
    )
    comment = fields.Text(
        string="Comment",
    )
    create_date = fields.Datetime(
        string="Date",
        readonly=True,
    )
