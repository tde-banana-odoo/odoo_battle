import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

import { Component, t, useProps } from "@odoo/owl";

const STATS = [
    { name: "menace", label: "M", title: _t("Menace") },
    { name: "size", label: "S", title: _t("Size") },
    { separator: true },
    { name: "rage", label: "R", title: _t("Rage") },
    { name: "willpower", label: "W", title: _t("Willpower") },
    { name: "gnosis", label: "G", title: _t("Gnosis") },
    { separator: true },
    { name: "damage", label: "D", title: _t("Damage") },
    { name: "resistance", label: "Res", title: _t("Resistance") },
];

/** Wargame-like statistics table: editable in forms, compact (display only) in lists */
export class BattleUnitStats extends Component {
    static template = "odoo_battle.BattleUnitStats";
    props = useProps({ ...standardWidgetProps, compact: t.boolean().optional() });

    get stats() {
        return STATS.map((stat) => ({ ...stat, value: this.props.record.data[stat.name] }));
    }

    onChange(name, ev) {
        this.props.record.update({ [name]: parseInt(ev.target.value, 10) || 0 });
    }
}

registry.category("view_widgets").add("battle_unit_stats", {
    component: BattleUnitStats,
    extractProps: ({ options }) => ({ compact: Boolean(options.compact) }),
    // readonly as defined on the model: editable on units and templates, not on related ones (e.g. solver lines)
    fieldDependencies: STATS.filter((stat) => stat.name).map(({ name }) => ({ name, type: "integer" })),
});
