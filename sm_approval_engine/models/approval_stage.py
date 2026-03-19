# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalStage(models.Model):
    """Individual stage within an approval workflow."""
    
    _name = "sm.approval.stage"
    _description = "SM Approval Stage"
    _order = "sequence, id"

    name = fields.Char(
        string="Stage Name",
        required=True,
    )
    config_id = fields.Many2one(
        comodel_name="sm.approval.config",
        string="Workflow",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        default=10,
    )
    
    # Approver Configuration
    approver_type = fields.Selection(
        selection=[
            ("user", "Specific User"),
            ("group", "User Group"),
            ("field", "Dynamic Field (from document)"),
            ("manager", "Requester's Manager"),
        ],
        string="Approver Type",
        required=True,
        default="user",
    )
    approver_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Approver User",
    )
    approver_group_id = fields.Many2one(
        comodel_name="res.groups",
        string="Approver Group",
    )
    approver_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Approver Field",
        domain="[('model_id', '=', parent.model_id), ('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]",
        help="Select a Many2one field pointing to res.users on the source document",
    )
    require_all_group_members = fields.Boolean(
        string="Require All Group Members",
        default=False,
        help="If checked, ALL members of the group must approve. "
             "Otherwise, any single member can approve.",
    )
    
    # Escalation
    escalation_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Escalation Contact",
        help="User to notify when this stage is overdue",
    )
    
    # Settings
    can_reject = fields.Boolean(
        string="Can Reject",
        default=True,
    )
    can_return = fields.Boolean(
        string="Can Return to Requester",
        default=True,
    )
    allow_delegation = fields.Boolean(
        string="Allow Delegation",
        default=False,
        help="Approver can delegate approval to another user",
    )
    rejection_reason_required = fields.Boolean(
        string="Rejection Reason Required",
        default=True,
    )

    @api.constrains("approver_type", "approver_user_id", "approver_group_id", "approver_field_id")
    def _check_approver_config(self):
        for stage in self:
            if stage.approver_type == "user" and not stage.approver_user_id:
                raise ValidationError(
                    _("Please select an approver user for stage '%s'.") % stage.name
                )
            elif stage.approver_type == "group" and not stage.approver_group_id:
                raise ValidationError(
                    _("Please select an approver group for stage '%s'.") % stage.name
                )
            elif stage.approver_type == "field" and not stage.approver_field_id:
                raise ValidationError(
                    _("Please select an approver field for stage '%s'.") % stage.name
                )

    def get_approvers(self, source_record):
        """Get the approver user(s) for this stage.
        
        Args:
            source_record: The document being approved
            
        Returns:
            res.users recordset
        """
        self.ensure_one()
        
        if self.approver_type == "user":
            return self.approver_user_id
            
        elif self.approver_type == "group":
            return self.approver_group_id.users
            
        elif self.approver_type == "field":
            if self.approver_field_id:
                field_name = self.approver_field_id.name
                if hasattr(source_record, field_name):
                    return getattr(source_record, field_name)
            return self.env["res.users"]
            
        elif self.approver_type == "manager":
            if hasattr(source_record, "create_uid"):
                employee = self.env["hr.employee"].search([
                    ("user_id", "=", source_record.create_uid.id)
                ], limit=1)
                if employee and employee.parent_id and employee.parent_id.user_id:
                    return employee.parent_id.user_id
            return self.env["res.users"]
        
        return self.env["res.users"]
