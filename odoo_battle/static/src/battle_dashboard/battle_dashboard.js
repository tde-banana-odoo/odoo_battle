import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

/** DM dashboard: current round, factions, battles to solve and solved */
export class BattleDashboard extends Component {
    static template = "odoo_battle.BattleDashboard";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: {} });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("battle.round", "get_dashboard_data", []);
    }

    openRecord(resModel, resId) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: resModel, res_id: resId, views: [[false, "form"]] });
    }

    openSolver(locationId) {
        this.action.doAction("odoo_battle.battle_solver_action", {
            additionalContext: { active_model: "battle.location", active_id: locationId },
            onClose: () => this.load(),
        });
    }

    async startNextRound() {
        await this.orm.call("battle.round", "action_start_next_round", []);
        await this.load();
    }
}

registry.category("actions").add("odoo_battle.dashboard", BattleDashboard);
