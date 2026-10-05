import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component, useProps } from "@odoo/owl";

/** Chevron folding / unfolding a section, stored in a boolean field */
export class BattleFoldToggle extends Component {
    static template = "odoo_battle.BattleFoldToggle";
    props = useProps(standardFieldProps);

    get folded() {
        return this.props.record.data[this.props.name];
    }

    get title() {
        return this.folded ? _t("Show units") : _t("Hide units");
    }

    onClick() {
        this.props.record.update({ [this.props.name]: !this.folded });
    }
}

registry.category("fields").add("battle_fold_toggle", {
    component: BattleFoldToggle,
    supportedTypes: ["boolean"],
});
