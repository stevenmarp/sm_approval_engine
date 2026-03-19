# -*- coding: utf-8 -*-
# Copyright 2026 Steven Marp

from odoo import api, fields, models, _


class SaleOrder(models.Model):
    """Add approval workflow capability to Sale Order."""
    
    _inherit = ["sale.order", "sm.approval.mixin"]
    _name = "sale.order"
    _approval_model = "sale.order"

    def _on_approval_complete(self, request):
        """Auto-confirm sale order when approval is complete."""
        super()._on_approval_complete(request)
        
        # Get config to check if auto-confirm is enabled
        config = request.config_id
        if config and config.on_approve_callback == "action_confirm":
            return  # Will be called by callback
        
        # Default: Post a message
        self.message_post(
            body=_("✅ Approval workflow completed. The order is now approved."),
            message_type="notification",
        )

    def _on_approval_rejected(self, request):
        """Handle rejection of sale order approval."""
        super()._on_approval_rejected(request)
        
        self.message_post(
            body=_("❌ Approval request was rejected. Reason: %s") % (
                request.rejection_reason or _("No reason provided")
            ),
            message_type="notification",
        )
