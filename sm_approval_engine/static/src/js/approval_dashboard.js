/** @odoo-module **/
/* Copyright 2026 Steven Marp */

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ApprovalDashboard extends Component {
    static template = "sm_approval_engine.ApprovalDashboard";
    // Accept all props from Odoo action system
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            stats: {
                pending: 0,
                approved: 0,
                rejected: 0,
                myPending: 0,
            },
            recentRequests: [],
            myApprovals: [],
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        try {
            // Call backend method to get all stats with proper sudo access
            const data = await this.orm.call(
                "sm.approval.request",
                "get_dashboard_stats",
                [],
                {}
            );
            
            this.state.stats = data.stats;
            this.state.recentRequests = data.recentRequests;
            this.state.myApprovals = data.myApprovals;
            this.state.loading = false;
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
            this.state.loading = false;
        }
    }

    async openMyApprovals() {
        return this.action.doAction("sm_approval_engine.action_sm_my_approvals");
    }

    async openAllRequests() {
        return this.action.doAction("sm_approval_engine.action_sm_approval_request");
    }

    async openPendingRequests() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Pending Requests",
            res_model: "sm.approval.request",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain: [["state", "=", "pending"]],
            target: "current",
        });
    }

    async openApprovedRequests() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Approved Requests",
            res_model: "sm.approval.request",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain: [["state", "=", "approved"]],
            target: "current",
        });
    }

    async openRejectedRequests() {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Rejected Requests",
            res_model: "sm.approval.request",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain: [["state", "=", "rejected"]],
            target: "current",
        });
    }

    async openWorkflows() {
        return this.action.doAction("sm_approval_engine.action_sm_approval_config");
    }

    async openRequest(requestId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "sm.approval.request",
            res_id: requestId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async quickApprove(requestId) {
        await this.orm.call("sm.approval.request", "action_approve", [[requestId]]);
        await this.loadDashboardData();
    }
}

// Register the dashboard as an action
registry.category("actions").add("sm_approval_dashboard", ApprovalDashboard);
