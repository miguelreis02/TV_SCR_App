"""
Testes da interface: construcao da janela, recolha e validacao dos inputs.

Nao testam o calculo (isso e o resto da suite) -- testam que a janela monta o
:class:`tvscr.RunScenario` certo a partir do formulario, que rejeita valores
invalidos com uma mensagem que identifica o campo, e que o painel de resultados
mostra os numeros que a biblioteca devolveu.

Sao automaticamente ignorados onde nao haja tkinter ou ecra disponivel.
"""

from __future__ import annotations

import dataclasses
import sys
import json
import struct
import time
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

tk = pytest.importorskip("tkinter")

from tvscr import (KineticParameters, KineticTuning, RunScenario,   # noqa: E402
                   VolumeSweepOptions)
from tvscr_ui.docs import (DOC_PATH, parse_inline, parse_markdown,   # noqa: E402
                           plain_text, slugify)
from tvscr_ui.main_window import (MODE_COLUMNS, PAGE_HELP,           # noqa: E402
                                  SUBSTRATE_COLUMNS, MainWindow)
from tvscr_ui.theme import C                                         # noqa: E402
from tvscr_ui.widgets import FieldError, format_number            # noqa: E402

CSV_INPUTS = Path(r"D:\IST\MeMEC\Tese\MATLAB - 1D Model\Modelos\Tronconi1998"
                  r"\Data Set\Tabela_Inputs_Final.csv")


@pytest.fixture(scope="module")
def window():
    """UMA janela para todos os testes.

    Criar e destruir varios ``Tk`` no mesmo processo e fragil (o interpretador
    Tcl perde o ``tk.tcl`` ao fim de algumas vezes), por isso a janela e
    partilhada e reposta entre testes pelo fixture ``_reset_form``.
    """
    try:
        win = MainWindow()
    except tk.TclError as exc:                     # sem ecra (CI headless)
        pytest.skip(f"sem ambiente grafico: {exc}")
    win.update()
    yield win
    win.destroy()


@pytest.fixture(autouse=True)
def _reset_form(window):
    """Repoe o formulario nos valores iniciais antes de cada teste."""
    window._apply(RunScenario(sweep=VolumeSweepOptions(fouling=0.15),
                              kinetics=KineticParameters(aging_KK0=0.80)))
    window.f_all_engines.set(False)
    window.f_engine.set_options([""])
    window._dataset = None
    window.form.select("motor")
    window.update()
    yield


def _pick_dg1(window) -> None:
    """Carrega o dataset e escolhe o DG1 (usado por varios testes)."""
    window.f_dataset.set(str(CSV_INPUTS))
    window._load_dataset()
    window.f_engine.set("DG1")
    window._on_engine_change()
    window.update()


def test_window_builds_with_all_sections(window):
    """Todos os campos existem e a janela sobrevive a um ciclo de eventos."""
    for name in ("f_dataset", "f_engine", "f_fuel", "f_pressure", "f_tier",
                 "f_cpsi", "f_wall", "f_length", "f_fouling", "f_sweep_substrate",
                 "f_k0ads", "f_KK0", "f_Deff", "f_Mbar",
                 "f_t_kNO", "f_cyc_frac", "f_mode_slip",
                 "f_v_max", "f_v_step", "f_v_min", "f_refine",
                 "f_alpha0", "f_dalpha", "f_minimize",
                 "f_nodes", "f_outdir", "f_save_csv", "f_save_png"):
        assert hasattr(window, name), f"falta o campo {name}"


def test_field_rejects_non_numeric_and_names_the_parameter(window):
    window.f_cpsi.set("abc")
    with pytest.raises(FieldError) as exc:
        window.f_cpsi.value()
    assert "Densidade celular" in str(exc.value)


def test_field_enforces_limits(window):
    window.f_fouling.set(1.5)                      # maximo e 0.99
    with pytest.raises(FieldError):
        window.f_fouling.value()


def test_length_is_required(window):
    """Sem volume instalado, o comprimento passou a ser input obrigatorio."""
    window.f_length.set("")
    with pytest.raises(FieldError):
        window.f_length.value()


def test_collect_refuses_without_dataset(window):
    window.f_dataset.set("")
    with pytest.raises(FieldError):
        window._collect()


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_collect_refuses_impossible_cell_geometry(window):
    _pick_dg1(window)
    window.f_wall.set(0.01)                        # parede maior que o passo
    with pytest.raises(FieldError) as exc:
        window._collect()
    assert "dh" in str(exc.value)


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_collect_refuses_inverted_alpha_limits(window):
    _pick_dg1(window)
    window.f_alpha_min.set(1.5)
    window.f_alpha_max.set(1.0)
    with pytest.raises(FieldError):
        window._collect()


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_loading_dataset_fills_engines_and_geometry(window):
    window.f_dataset.set(str(CSV_INPUTS))
    window._load_dataset()
    window.update()

    assert list(window.f_engine.combo.cget("values")) == \
        ["DG1", "DG2", "DG3", "DG4", "DG5"]

    window.f_engine.set("DG1")
    window._on_engine_change()
    assert float(window.f_length.raw()) == pytest.approx(1.2)


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_collect_builds_the_expected_scenario(window):
    _pick_dg1(window)
    window.f_power_law.set(True)
    window.update()

    scenario, engine = window._collect()

    assert engine == "DG1"
    assert scenario.engines == ["DG1"]
    assert scenario.substrate.cpsi == pytest.approx(46.0)
    assert scenario.substrate.wall_thickness_m == pytest.approx(0.43e-3)
    assert scenario.sweep.fouling == pytest.approx(0.15)
    assert scenario.kinetics.aging_KK0 == pytest.approx(0.80)
    assert scenario.tier_power_law_only is True
    assert scenario.targets.cycle_NO_frac == pytest.approx(0.60)
    assert scenario.alpha_loop.alpha0 == pytest.approx(0.80)
    assert scenario.solver.n_nodes == 120
    assert scenario.length_m == pytest.approx(1.2)
    # a area de referencia e o MAIOR volume do varrimento a dividir por L
    assert scenario.frontal_area_m2 == pytest.approx(
        scenario.sweep.volume_max_m3 / 1.2)

    # o cenario recolhido tem de ser um caso valido para a biblioteca
    cases = scenario.build_cases()
    assert len(cases) == 1 and cases[0].name == "DG1"
    assert cases[0].geometry.fouling == 0.0          # o fouling e do varrimento


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_run_all_engines_uses_one_geometry_for_all(window):
    window.f_dataset.set(str(CSV_INPUTS))
    window._load_dataset()
    window.f_all_engines.set(True)
    window.update()

    scenario, engine = window._collect()
    assert engine is None
    assert scenario.engines is None                  # todos os do ficheiro
    # L e a malha de volumes sao escolha de projeto: aplicam-se a todos
    assert scenario.length_m == pytest.approx(float(window.f_length.raw()))


def test_scenario_roundtrip_through_the_form(window):
    scenario = RunScenario(
        dataset_path=str(CSV_INPUTS),
        tuning=KineticTuning(kNO=1.3, kads=0.9, Deff=1.1, k0d=0.8))
    window._apply(scenario)
    window.update()

    assert float(window.f_t_kNO.raw()) == pytest.approx(1.3)
    assert float(window.f_t_kads.raw()) == pytest.approx(0.9)
    assert float(window.f_nodes.raw()) == 120


# --------------------------------------------------------------------- #
#  Paginas (seccoes escondidas)
# --------------------------------------------------------------------- #
def test_all_eight_sections_are_pages(window):
    assert window.form.keys == ["motor", "geometria", "alvos", "cinetica",
                                "calibracao", "varrimento", "alpha", "saida"]
    assert window.form.current == "motor"


def _topmost_page(window):
    """A pagina no topo da pilha e o ultimo filho da area (ordem de empilhamento)."""
    return window.form.area.winfo_children()[-1]


@pytest.mark.parametrize("key", ["motor", "geometria", "alvos", "cinetica",
                                 "calibracao", "varrimento", "alpha", "saida"])
def test_selected_page_is_the_one_on_top(window, key):
    """Regressao: as paginas criadas depois tapavam a que estava seleccionada."""
    window.form.select(key)
    window.update()
    assert window.form.current == key
    assert _topmost_page(window) is window.form.page(key)


def test_page_one_is_visible_by_default(window):
    """A pagina 1 tem de estar mesmo visivel, e nao apenas com o separador aceso."""
    assert window.form.current == "motor"
    assert _topmost_page(window) is window.form.page("motor")


# --------------------------------------------------------------------- #
#  Roda do rato
# --------------------------------------------------------------------- #
def _wheel_event(widget, delta=-120):
    """Evento de roda com o ponteiro no centro do widget dado."""
    return types.SimpleNamespace(
        x_root=widget.winfo_rootx() + widget.winfo_width() // 2,
        y_root=widget.winfo_rooty() + widget.winfo_height() // 2,
        delta=delta)


def test_console_is_not_part_of_the_form(window):
    """Regressao: rolar na consola mexia tambem o formulario.

    Testa a decisao directamente (a que widget pertence o ponteiro), e nao via
    ``winfo_containing``, que depende de a janela estar mesmo visivel no ecra.
    """
    assert window._is_inside_form(window.console.text) is False
    assert window._is_inside_form(window.console) is False
    assert window._is_inside_form(window.btn_run) is False


def test_form_widgets_are_part_of_the_form(window):
    assert window._is_inside_form(window._form_canvas) is True
    assert window._is_inside_form(window.f_cpsi.entry) is True
    assert window._is_inside_form(window.mode_table) is True


def test_wheel_over_console_leaves_the_form_where_it_was(window):
    for i in range(80):
        window.console.write(f"linha {i}")
    window.update()
    before = window._form_canvas.yview()[0]
    assert window._on_mousewheel(_wheel_event(window.console.text)) is None
    window.update()
    assert window._form_canvas.yview()[0] == before


# --------------------------------------------------------------------- #
#  Introducao manual dos dados do motor
# --------------------------------------------------------------------- #
MANUAL_MODES = [
    {"load_pct": 11.0, "weight": 10.5, "power_kW": 637.0, "T_in_C": 341.6,
     "NO_in_ppm": 530.0, "sfoc_g_per_kWh": 229.5, "lambda_": 3.42},
    {"load_pct": 50.0, "weight": 31.6, "power_kW": 2895.0, "T_in_C": 410.4,
     "NO_in_ppm": 1160.0, "sfoc_g_per_kWh": 208.0, "lambda_": 2.37},
    {"load_pct": 73.0, "weight": 26.3, "power_kW": 4213.0, "T_in_C": 421.5,
     "NO_in_ppm": 1228.0, "sfoc_g_per_kWh": 197.0, "lambda_": 2.18},
]


def _fill_manual(window, modes=None):
    window.source.set("manual")
    window._update_source_state()
    window.f_manual_name.set("MOTOR-X")
    window.f_manual_rpm.set(513.0)
    window.f_length.set(1.2)
    window.mode_table.set_rows(modes if modes is not None else MANUAL_MODES)
    window.update()


def test_manual_entry_builds_a_valid_case(window):
    _fill_manual(window)
    scenario, engine = window._collect()

    assert engine == "MOTOR-X"
    assert scenario.dataset_path is None
    assert len(scenario.inline_engines) == 1
    spec = scenario.inline_engines[0]
    assert len(spec["modes"]) == 3
    assert spec["modes"][0]["T_in_K"] == pytest.approx(341.6 + 273.15)

    case = scenario.build_cases()[0]
    assert case.name == "MOTOR-X"
    assert case.n_modes == 3
    assert case.geometry.length_m == pytest.approx(1.2)
    assert case.nox_limit_gkWh == pytest.approx(9 * 513 ** -0.2, rel=1e-9)
    assert (case.mass_flow_kgs > 0).all()


def test_manual_entry_ignores_blank_rows(window):
    _fill_manual(window)
    window.mode_table.add_row()          # linha vazia no fim
    window.update()
    scenario, _ = window._collect()
    assert len(scenario.inline_engines[0]["modes"]) == 3


def test_manual_entry_requires_the_exhaust_flow(window):
    modes = [dict(m) for m in MANUAL_MODES]
    modes[1].pop("sfoc_g_per_kWh")       # sem SFOC e sem caudal
    _fill_manual(window, modes)
    with pytest.raises(FieldError) as exc:
        window._collect()
    assert "Modo 2" in str(exc.value)


def test_manual_entry_accepts_the_exhaust_flow_directly(window):
    modes = []
    for i, m in enumerate(MANUAL_MODES):
        row = {k: v for k, v in m.items()
               if k not in ("sfoc_g_per_kWh", "lambda_")}
        row["exhaust_mass_flow_kgs"] = 2.0 + i
        modes.append(row)
    _fill_manual(window, modes)

    scenario, _ = window._collect()
    case = scenario.build_cases()[0]
    np.testing.assert_allclose(case.mass_flow_kgs, [2.0, 3.0, 4.0])


def test_manual_entry_needs_the_length(window):
    _fill_manual(window)
    window.f_length.set("")
    with pytest.raises(FieldError) as exc:
        window._collect()
    assert "Comprimento" in str(exc.value)


def test_manual_scenario_survives_a_json_roundtrip(window):
    _fill_manual(window)
    scenario, _ = window._collect()
    data = json.loads(json.dumps(scenario.to_dict(), default=str))
    back = RunScenario.from_dict(data)

    assert back.build_cases()[0].n_modes == 3
    window._apply(back)
    window.update()
    assert window.source.get() == "manual"
    assert window.f_manual_name.raw() == "MOTOR-X"
    assert window.mode_table.n_rows == 3


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_copy_from_dataset_fills_the_manual_table(window):
    _pick_dg1(window)
    window.source.set("manual")
    window._update_source_state()
    window._copy_from_dataset()
    window.update()

    assert window.mode_table.n_rows == 4
    assert window.f_manual_name.raw() == "DG1"

    scenario, _ = window._collect()
    manual_case = scenario.build_cases()[0]

    window.source.set("csv")
    window._update_source_state()
    csv_scenario, _ = window._collect()
    csv_case = csv_scenario.build_cases()[0]

    # o caminho manual tem de reproduzir exactamente o do ficheiro
    np.testing.assert_allclose(manual_case.mass_flow_kgs, csv_case.mass_flow_kgs,
                               rtol=1e-9)
    np.testing.assert_allclose(manual_case.T_K, csv_case.T_K, rtol=1e-12)
    assert manual_case.nox_limit_gkWh == pytest.approx(csv_case.nox_limit_gkWh)


# --------------------------------------------------------------------- #
#  Alinhamento da tabela
# --------------------------------------------------------------------- #
def test_table_header_and_cells_live_in_one_grid(window):
    """Regressao: cabecalho e celulas estavam em frames diferentes e nao alinhavam."""
    table = window.mode_table
    assert all(w.master is table for w in table.winfo_children())

    for i, _col in enumerate(table.columns):
        header = table.grid_slaves(row=0, column=i + 1)
        unit = table.grid_slaves(row=1, column=i + 1)
        cell = table.grid_slaves(row=2, column=i + 1)
        assert header and unit and cell, f"coluna {i} incompleta"


def test_table_columns_are_visually_aligned(window):
    """O centro de cada cabecalho coincide com o centro da celula por baixo."""
    table = window.mode_table
    window.form.select("motor")
    window.source.set("manual")
    window._update_source_state()
    window.update_idletasks()

    for i, col in enumerate(table.columns):
        header = table.grid_slaves(row=0, column=i + 1)[0]
        cell = table.grid_slaves(row=2, column=i + 1)[0]
        centre_header = header.winfo_x() + header.winfo_width() / 2
        centre_cell = cell.winfo_x() + cell.winfo_width() / 2
        assert abs(centre_header - centre_cell) <= 1.0, \
            f'coluna "{col.label}" desalinhada'


# --------------------------------------------------------------------- #
#  Indicadores desenhados (bola preta / visto preto)
# --------------------------------------------------------------------- #
def test_radio_indicator_shows_a_dot_only_when_selected(window):
    radio = window.source_radio
    window.source.set("csv")
    window.update_idletasks()
    # circulo apenas quando nao escolhido; circulo + ponto quando escolhido
    assert len(radio._indicators["csv"].find_all()) == 2
    assert len(radio._indicators["manual"].find_all()) == 1

    window.source.set("manual")
    window.update_idletasks()
    assert len(radio._indicators["csv"].find_all()) == 1
    assert len(radio._indicators["manual"].find_all()) == 2


def test_check_indicator_shows_a_mark_only_when_on(window):
    check = window.f_sweep_substrate
    check.set(False)
    window.update_idletasks()
    assert len(check.box.find_all()) == 1              # so a caixa

    check.set(True)
    window.update_idletasks()
    assert len(check.box.find_all()) == 3              # caixa + duas linhas do visto


def test_clicking_the_check_label_toggles_it(window):
    check = window.f_sweep_substrate
    check.set(False)
    check.toggle()
    assert check.value() is True


# --------------------------------------------------------------------- #
#  Varrimento de substratos
# --------------------------------------------------------------------- #
def test_substrate_sweep_is_off_by_default(window):
    assert window.f_sweep_substrate.value() is False


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_collect_without_substrate_sweep_has_no_substrates(window):
    _pick_dg1(window)
    scenario, _ = window._collect()
    assert scenario.substrates is None
    assert scenario.substrate.cpsi == pytest.approx(46.0)


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_collect_with_substrate_sweep_lists_the_pairs(window):
    _pick_dg1(window)
    window.f_sweep_substrate.set(True)
    window.substrate_table.set_rows([{"cpsi": 46, "wall_mm": 0.43},
                                     {"cpsi": 100, "wall_mm": 0.25}])
    window.update()

    scenario, _ = window._collect()
    assert scenario.substrates == [
        {"cpsi": 46.0, "wall_thickness_m": pytest.approx(0.43e-3)},
        {"cpsi": 100.0, "wall_thickness_m": pytest.approx(0.25e-3)}]
    # o substrato base tem de ser um dos pares utilizaveis
    assert scenario.substrate.cpsi == pytest.approx(46.0)


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_impossible_pair_does_not_block_the_run(window):
    """Um par impossivel entre outros validos e problema do varrimento, nao do input."""
    _pick_dg1(window)
    window.f_sweep_substrate.set(True)
    window.substrate_table.set_rows([{"cpsi": 46, "wall_mm": 0.43},
                                     {"cpsi": 400, "wall_mm": 5.0}])
    window.update()
    scenario, _ = window._collect()
    assert len(scenario.substrates) == 2


@pytest.mark.skipif(not CSV_INPUTS.is_file(), reason="dataset nao disponivel")
def test_all_pairs_impossible_is_refused(window):
    _pick_dg1(window)
    window.f_sweep_substrate.set(True)
    window.substrate_table.set_rows([{"cpsi": 400, "wall_mm": 5.0},
                                     {"cpsi": 900, "wall_mm": 4.0}])
    window.update()
    with pytest.raises(FieldError) as exc:
        window._collect()
    assert "dh" in str(exc.value)
    assert window.form.current == "geometria"


def test_substrate_sweep_survives_a_scenario_roundtrip(window):
    window.f_sweep_substrate.set(True)
    window.substrate_table.set_rows([{"cpsi": 64, "wall_mm": 0.35}])
    window.update()

    scenario = RunScenario(substrates=[{"cpsi": 64, "wall_thickness_m": 0.35e-3}])
    window._apply(scenario)
    window.update()

    assert window.f_sweep_substrate.value() is True
    assert window.substrate_table.n_rows == 1
    rows = window.substrate_table.rows()
    assert rows[0]["cpsi"] == pytest.approx(64)
    assert rows[0]["wall_mm"] == pytest.approx(0.35)


# --------------------------------------------------------------------- #
#  Caudal de escape (porte de get_mass_dot_v3.m)
# --------------------------------------------------------------------- #
def test_no_measured_outlet_column_in_the_manual_table(window):
    """O NO a saida e output do modelo, nao input: a coluna saiu da tabela."""
    keys = [c.key for c in window.mode_table.columns]
    assert "NO_out_ppm" not in keys
    assert "NO_in_ppm" in keys


def test_exhaust_flow_button_fills_the_column(window):
    _fill_manual(window)
    window._fill_exhaust_flow()
    window.update()

    rows = window.mode_table.rows()
    assert all(r["exhaust_mass_flow_kgs"] is not None for r in rows)

    from tvscr import exhaust_flow
    expected = exhaust_flow([229.5, 208.0, 197.0], [637.0, 2895.0, 4213.0],
                            [3.42, 2.37, 2.18], "HFO").exhaust_mass_flow_kgs
    np.testing.assert_allclose([r["exhaust_mass_flow_kgs"] for r in rows],
                               expected, rtol=1e-9)


def test_exhaust_flow_button_says_which_mode_is_missing_data(window, monkeypatch):
    seen = {}
    monkeypatch.setattr("tvscr_ui.main_window.messagebox.showinfo",
                        lambda title, msg, **k: seen.update(title=title, msg=msg))
    modes = [dict(m) for m in MANUAL_MODES]
    modes[1].pop("lambda_")
    _fill_manual(window, modes)
    window._fill_exhaust_flow()
    assert "2" in seen.get("msg", "")


# --------------------------------------------------------------------- #
#  Layout: barra lateral, paginas e cartoes
# --------------------------------------------------------------------- #
def test_tabs_are_grouped_in_the_sidebar(window):
    """Os oito separadores estao na barra lateral, em tres grupos com titulo."""
    groups = [w.cget("text") for w in window.form.tabs.winfo_children()
              if isinstance(w, tk.Label)]
    assert groups == ["DADOS DO PROJETO", "MODELO DO CATALISADOR", "CÁLCULO"]
    # a barra lateral nao rola com o formulario
    assert window._is_inside_form(window.form.tabs) is False


def test_only_the_selected_page_takes_space(window):
    """Uma pagina alta nao pode obrigar as outras a rolar."""
    window.form.select("cinetica")
    window.update()
    for key in window.form.keys:
        in_grid = window.form.page(key).winfo_manager() == "grid"
        assert in_grid is (key == "cinetica"), key


def test_next_and_previous_walk_the_pages_in_order(window):
    window.form.select("motor")
    visited = ["motor"]
    for _ in range(len(window.form.keys) - 1):
        window.form.select_next()
        visited.append(window.form.current)
    assert visited == window.form.keys

    window.form.select_next()                       # nao passa do fim
    assert window.form.current == "saida"
    window.form.select_previous()
    assert window.form.current == "alpha"


def test_mode_table_only_takes_space_in_manual_entry(window):
    window.source.set("csv")
    window.update()
    assert window._modes_card.winfo_manager() == ""
    assert window._csv_frame.winfo_manager() == "grid"

    window.source.set("manual")
    window.update()
    assert window._modes_card.winfo_manager() == "grid"
    assert window._csv_frame.winfo_manager() == ""


def test_unit_has_its_own_column_after_the_field(window):
    """Rotulo, campo e unidade em colunas fixas: os campos ficam alinhados."""
    field = window.f_pressure
    assert field.label.cget("text") == "Pressão"
    assert field.unit_label.cget("text") == "Pa"
    assert (int(field.unit_label.grid_info()["column"])
            > int(field.entry.grid_info()["column"])
            > int(field.label.grid_info()["column"]))
    assert window.f_fouling.unit_label.cget("text") == "–"   # adimensional


def test_parameters_with_help_show_a_marker(window):
    assert window.f_KK0.help is not None            # tem explicacao
    assert window.f_k0NO.help is None               # nao tem


@pytest.mark.parametrize("value, text", [
    (2.5e10, "2.5e10"), (8.5e6, "8.5e6"), (8.0e8, "8e8"),
    (101325.0, "101325"), (18.6e3, "18600"), (0.43e-3, "0.00043"),
    (1e-4, "0.0001"), (1e-6, "1e-6"), (8e-5, "8e-5"), (0.02896, "0.02896"),
    (0.8, "0.8"), (1.0, "1"), (0.0, "0"), (-2.5e-7, "-2.5e-7"),
    (120, "120"), (None, ""), ("DG1", "DG1"),
])
def test_numbers_are_shown_in_a_readable_form(value, text):
    assert format_number(value) == text


def test_shown_numbers_read_back_exactly(window):
    """A forma curta e so apresentacao: o valor lido e o mesmo, bit a bit."""
    k = KineticParameters()
    for field, value in ((window.f_k0ads, k.k0ads), (window.f_k0NO, k.k0NO),
                         (window.f_k0d, k.k0d), (window.f_Deff, k.Deff),
                         (window.f_Dmol, k.Dmol), (window.f_Mbar, k.M_bar_kg_mol),
                         (window.f_wall, 0.43e-3), (window.f_v_step, 1.0 / 3.0)):
        field.set(value)
        assert field.value() == value


# --------------------------------------------------------------------- #
#  Valor invalido: a janela leva o utilizador ao campo
# --------------------------------------------------------------------- #
def test_invalid_field_opens_its_page_and_flags_it(window, monkeypatch):
    shown = []
    monkeypatch.setattr("tvscr_ui.main_window.messagebox.showerror",
                        lambda title, msg, **k: shown.append(msg))
    _fill_manual(window)
    window.form.select("motor")
    window.f_KK0.set("abc")                         # campo de outro separador

    assert window._collect_or_report() is None
    assert "Envelhecimento KK0" in shown[0]
    assert window.form.current == "cinetica"
    assert window.form.is_flagged("cinetica")

    window.f_KK0.set(0.8)
    assert window._collect_or_report() is not None
    assert not any(window.form.is_flagged(key) for key in window.form.keys)


def test_invalid_table_cell_opens_the_engine_page(window, monkeypatch):
    monkeypatch.setattr("tvscr_ui.main_window.messagebox.showerror",
                        lambda *a, **k: None)
    modes = [dict(m) for m in MANUAL_MODES]
    modes[2].pop("power_kW")
    _fill_manual(window, modes)
    window.form.select("saida")

    assert window._collect_or_report() is None
    assert window.form.current == "motor"
    assert window.form.is_flagged("motor")
    window.form.clear_flags()


# --------------------------------------------------------------------- #
#  Painel de resultados
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def sweep_result(window):
    """Um varrimento verdadeiro (motor de tres modos), corrido uma so vez."""
    _fill_manual(window)
    scenario, engine = window._collect()
    return scenario.run_one(engine)


def test_results_panel_has_the_console_as_one_of_its_tabs(window):
    assert window.console is window.results.console
    for key in ("resumo", "modos", "varrimento", "grafico", "registo"):
        window.results.select(key)
        assert window.results.current == key
    window.results.select("resumo")


def test_summary_shows_the_critical_volume_next_to_the_targets(window,
                                                               sweep_result):
    panel = window.results
    panel.show_volume([sweep_result])
    window.update()
    crit = sweep_result.at_critical()

    assert panel.has_results
    assert panel.tile_volume.value_text == \
        f"{sweep_result.critical_volume_m3:.3f} m³"
    assert f"{sweep_result.critical_area_m2:.3f}" in panel.tile_volume.note_text
    assert panel.tile_nox.value_text.startswith(f"{crit['NOx_ciclo_gkWh']:.4f}")
    assert f"{sweep_result.targets.cycle_NO_gkWh:.4f}" in panel.tile_nox.note_text
    assert panel.tile_slip.value_text.startswith(f"{crit['slip_ciclo_ppm']:.3f}")
    # um resultado so: nao ha tabela de comparacao
    assert panel._compare.winfo_manager() == ""


def test_modes_table_has_one_row_per_mode(window, sweep_result):
    panel = window.results
    panel.show_volume([sweep_result])
    rows = panel.modes_tree.get_children()
    assert len(rows) == len(sweep_result.load_pct)
    j = sweep_result.critical_index
    assert panel.modes_tree.set(rows[0], "alpha") == f"{sweep_result.alpha[j, 0]:.3f}"


def test_sweep_table_has_one_row_per_volume_and_marks_the_critical(window,
                                                                   sweep_result):
    panel = window.results
    panel.show_volume([sweep_result])
    tree = panel.sweep_tree
    rows = tree.get_children()
    assert len(rows) == sweep_result.volume_m3.size

    volumes = [float(tree.set(row, "v")) for row in rows]
    assert volumes == sorted(volumes, reverse=True)

    critical = [row for row in rows if "critico" in tree.item(row, "tags")]
    assert len(critical) == 1
    assert float(tree.set(critical[0], "v")) == pytest.approx(
        sweep_result.critical_volume_m3, abs=1e-3)
    failed = [row for row in rows if "falha" in tree.item(row, "tags")]
    assert len(failed) == int((~sweep_result.ok).sum())


def test_summary_says_so_when_no_volume_is_admissible(window):
    _fill_manual(window)
    v_max = window.f_v_max.raw()
    window.f_v_max.set(0.6)                         # pequeno de mais
    try:
        scenario, engine = window._collect()
    finally:
        window.f_v_max.set(v_max)        # o reset entre testes nao repoe este campo
    result = scenario.run_one(engine)
    assert not np.isfinite(result.critical_volume_m3)

    panel = window.results
    panel.show_volume([result])
    assert panel.tile_volume.value_text == "Sem solução"
    assert "0.60" in panel.tile_volume.note_text
    assert panel.tile_nox.value_text == "—"
    # os modos mostrados sao os do maior volume avaliado
    assert len(panel.modes_tree.get_children()) == len(result.load_pct)


def test_several_results_are_compared_and_one_can_be_picked(window, sweep_result):
    other = dataclasses.replace(sweep_result, engine="MOTOR-Y")
    panel = window.results
    panel.select("resumo")
    panel.show_volume([sweep_result, other])
    window.update()

    assert len(panel.items_tree.get_children()) == 2
    assert panel._compare.winfo_manager() == "grid"
    assert panel.selected_title == sweep_result.engine

    panel.items_tree.selection_set("1")
    window.update()
    assert panel.selected_title == "MOTOR-Y"
    assert "MOTOR-Y" in panel.tile_volume.caption_text


def test_substrate_comparison_marks_the_smallest_volume(window):
    _fill_manual(window)
    window.f_sweep_substrate.set(True)
    window.substrate_table.set_rows([{"cpsi": 46, "wall_mm": 0.43},
                                     {"cpsi": 400, "wall_mm": 5.0}])  # impossivel
    scenario, _ = window._collect()
    sweep = scenario.run_substrate_sweep()

    panel = window.results
    panel.show_substrates(sweep)
    window.update()
    tree = panel.items_tree
    rows = tree.get_children()
    assert len(rows) == 2
    assert "★" in tree.set(rows[0], "obs")
    assert "falha" in tree.item(rows[1], "tags")
    assert panel.selected_title.startswith("MOTOR-X · CPSI 46")


def test_clearing_goes_back_to_the_empty_state(window, sweep_result):
    panel = window.results
    panel.show_volume([sweep_result])
    panel.clear()
    assert panel.has_results is False
    assert panel.selected_title is None
    assert not panel.sweep_tree.get_children()


def test_log_tab_is_marked_when_text_arrives_while_hidden(window):
    panel = window.results
    panel.select("registo")
    panel.select("resumo")
    assert panel.log_unread is False

    window.console.write("linha nova")
    assert panel.log_unread is True
    panel.select("registo")
    assert panel.log_unread is False
    panel.select("resumo")


def test_plot_is_drawn_to_the_size_of_the_panel(sweep_result):
    pytest.importorskip("matplotlib")
    from tvscr_ui.results import _figure_png

    for size in ((900, 240), (1000, 520)):          # numa linha e em 2x2
        png = _figure_png(sweep_result, *size)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", png[16:24]) == size


def test_running_ends_on_the_summary(window, monkeypatch):
    """Do botao ao resultado: registo durante o calculo, resumo no fim."""
    monkeypatch.setattr("tvscr_ui.main_window.messagebox.askyesno",
                        lambda *a, **k: True)       # sem pasta de resultados
    _fill_manual(window)
    window._on_run()
    assert window._running
    assert window.results.current == "registo"

    deadline = time.time() + 120
    while window._running and time.time() < deadline:
        window.update()
        time.sleep(0.02)

    assert not window._running
    assert window.results.current == "resumo"
    assert window.results.has_results
    assert window.results.tile_volume.value_text.endswith("m³")
    assert window.status.cget("text").startswith("Concluído")
    assert "VOLUME CRÍTICO" in window.console.dump()
    window.results.clear()


# --------------------------------------------------------------------- #
#  Documentacao: leitura do Markdown (nao precisa de janela)
# --------------------------------------------------------------------- #
SAMPLE_MD = """# Título do documento

Parágrafo com **negrito**, *itálico*, `código` e uma
[ligação](#secção-a) na mesma frase.

## Secção A

- primeiro item
  continua na linha seguinte
- segundo item
  1. item numerado, dentro

> Uma citação
> em duas linhas.

| campo | valor |
|---|---|
| `x` | **1** |
| y | a \\| b |

```
codigo | com barra
```

---

## Secção A
"""


def test_markdown_is_split_into_the_expected_blocks():
    blocks = parse_markdown(SAMPLE_MD)
    assert [b.kind for b in blocks] == [
        "heading", "paragraph", "heading", "list", "list", "list", "quote",
        "table", "code", "rule", "heading"]

    assert (blocks[0].level, blocks[2].level) == (1, 2)
    assert plain_text(blocks[3].spans) == "primeiro item continua na linha seguinte"
    assert (blocks[4].level, blocks[5].level) == (0, 1)       # lista dentro de lista
    assert (blocks[3].marker, blocks[5].marker) == ("•", "1.")
    assert plain_text(blocks[6].spans) == "Uma citação em duas linhas."
    assert blocks[8].text == "codigo | com barra"            # a barra nao faz tabela

    table = blocks[7].rows
    assert [[plain_text(cell) for cell in row] for row in table] == [
        ["campo", "valor"], ["x", "1"], ["y", "a | b"]]
    assert table[1][0][0].code and table[1][1][0].bold


def test_inline_styles_and_links_are_recognised():
    spans = parse_markdown(SAMPLE_MD)[1].spans
    by_text = {s.text: s for s in spans}
    assert by_text["negrito"].bold and not by_text["negrito"].italic
    assert by_text["itálico"].italic
    assert by_text["código"].code
    assert by_text["ligação"].link == "#secção-a"
    assert plain_text(spans).startswith("Parágrafo com negrito, itálico, código")

    nested = parse_inline("**[README](README.md)** e `a*b*c`")
    assert nested[0].bold and nested[0].link == "README.md"
    assert nested[-1].code and nested[-1].text == "a*b*c"    # sem italico no codigo


def test_heading_anchors_follow_the_github_rule():
    assert slugify("4. O ecrã") == "4-o-ecrã"
    assert slugify("1 · Dados do motor") == "1--dados-do-motor"
    assert slugify("14. Ficheiro de cenário (.json)") == "14-ficheiro-de-cenário-json"
    # titulos repetidos recebem sufixo, como no GitHub
    anchors = [b.anchor for b in parse_markdown(SAMPLE_MD) if b.kind == "heading"]
    assert anchors == ["título-do-documento", "secção-a", "secção-a-1"]


# --------------------------------------------------------------------- #
#  Documentacao: o INSTRUCOES.md como documentacao oficial
# --------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def manual():
    """O texto e os blocos do INSTRUCOES.md."""
    text = DOC_PATH.read_text(encoding="utf-8")
    return text, parse_markdown(text)


def _all_spans(blocks):
    for block in blocks:
        yield from block.spans
        for row in block.rows:
            for cell in row:
                yield from cell


def test_every_link_in_the_documentation_leads_somewhere(manual):
    """Indice e remissoes: nenhuma ligacao pode apontar para o vazio."""
    _text, blocks = manual
    anchors = {b.anchor for b in blocks if b.kind == "heading"}
    links = {s.link for s in _all_spans(blocks) if s.link}
    assert len(links) > 20                           # o indice esta la

    for link in links:
        if link.startswith("#"):
            assert link[1:] in anchors, f"ancora inexistente: {link}"
        elif "://" not in link:
            assert (DOC_PATH.parent / link.split("#")[0]).is_file(), link


def test_documentation_has_the_reference_sections(manual):
    _text, blocks = manual
    titles = " | ".join(plain_text(b.spans) for b in blocks
                        if b.kind == "heading" and b.level == 2)
    for expected in ("O ecrã", "Os campos, um a um", "Ler os resultados",
                     "Modelo e método de cálculo", "Ficheiro de inputs (CSV)",
                     "Ficheiros de saída", "Ficheiro de cenário (.json)",
                     "Pressupostos e limitações", "Nomenclatura", "Referências"):
        assert expected in titles, f"falta a secção «{expected}»"


def test_documentation_explains_every_field_of_the_form(window, manual):
    """Um parametro novo no formulario tem de entrar na documentacao."""
    text, _blocks = manual
    labels = {getattr(window, name).label_text for name in dir(window)
              if name.startswith("f_") and hasattr(getattr(window, name),
                                                   "label_text")}
    labels |= {column.label for column in MODE_COLUMNS + SUBSTRATE_COLUMNS}
    assert len(labels) > 50
    missing = sorted(label for label in labels if label not in text)
    assert not missing, f"campos sem documentação: {missing}"


def test_documentation_states_the_defaults_of_the_form(window, manual):
    """Os valores por omissao escritos na documentacao sao os da aplicacao."""
    _text, blocks = manual
    documented = {}
    for block in blocks:
        if block.kind == "table" and "omissão" in [plain_text(c) for c in block.rows[0]]:
            column = [plain_text(c) for c in block.rows[0]].index("omissão")
            for row in block.rows[1:]:
                documented[plain_text(row[0])] = plain_text(row[column])

    for name in ("f_pressure", "f_cpsi", "f_wall", "f_length", "f_cyc_frac",
                 "f_mode_frac", "f_cyc_slip", "f_mode_slip", "f_k0ads", "f_Eads",
                 "f_k0NO", "f_ENO", "f_k0d", "f_E0d", "f_beta", "f_KK0",
                 "f_fouling", "f_Deff", "f_Dmol", "f_Mbar", "f_f", "f_t_kNO",
                 "f_v_max", "f_v_step", "f_v_min", "f_refine_tol", "f_alpha0",
                 "f_dalpha", "f_alpha_min", "f_alpha_max", "f_max_iter",
                 "f_bracket_tol", "f_nodes", "f_manual_rpm"):
        field = getattr(window, name)
        written = documented[field.label_text].split()[0]
        assert float(written) == pytest.approx(field.value()), field.label_text


def test_help_key_targets_exist_for_every_page(window, manual):
    _text, blocks = manual
    anchors = {b.anchor for b in blocks if b.kind == "heading"}
    assert set(PAGE_HELP) == set(window.form.keys)
    assert set(PAGE_HELP.values()) <= anchors


# --------------------------------------------------------------------- #
#  Documentacao: o separador na aplicacao
# --------------------------------------------------------------------- #
def test_documentation_tab_takes_the_place_of_the_work_area(window):
    window.form.select("geometria")
    assert window.docs_visible is False

    window.show_docs()
    window.update()
    assert window.docs_visible is True
    assert window.docs_link.active is True
    assert window._paned.winfo_manager() == ""        # o formulario cedeu o lugar
    assert window.docs.path == DOC_PATH
    assert window.docs.toc.size() > 30                # indice com as seccoes
    assert window.form.current == "geometria"         # a pagina nao mudou

    window.form.select("alvos")                       # um separador volta atras
    window.update()
    assert window.docs_visible is False
    assert window.docs_link.active is False
    assert window._paned.winfo_manager() == "pack"
    assert window.form.current == "alvos"


def test_nothing_in_the_form_is_lost_while_reading(window):
    window.f_cpsi.set(64)
    window.show_docs()
    window.show_work()
    assert window.f_cpsi.value() == 64


def test_help_key_opens_the_section_of_the_current_page(window):
    window.form.select("cinetica")
    window._on_help_key()
    window.update()
    assert window.docs_visible
    assert window.docs.current_anchor() == PAGE_HELP["cinetica"]


def test_documentation_search_covers_text_and_tables(window):
    window.show_docs()
    window.update()
    docs = window.docs
    docs.query.set("fouling")
    total = docs.find()
    kinds = {hit[1] for hit in docs._hits}
    assert total > 10
    assert kinds == {"text", "cell"}                  # texto corrido e tabelas
    assert docs._count.cget("text") == f"1 de {total}"

    docs.find(forward=False)                          # da a volta para o fim
    assert docs._count.cget("text") == f"{total} de {total}"

    docs.query.set("palavraquenaoexiste")
    assert docs.find() == 0
    assert docs._count.cget("text") == "sem resultados"
    docs.query.set("")
    docs.find()


def test_links_to_other_project_files_open_in_the_reader(window):
    window.show_docs()
    docs = window.docs
    docs.follow("README.md")
    window.update()
    assert docs.path.name == "README.md"
    assert docs.btn_home.winfo_manager() == "pack"    # ha por onde voltar

    docs.load(docs.home)
    window.update()
    assert docs.path == DOC_PATH
    assert docs.btn_home.winfo_manager() == ""


def test_missing_documentation_is_reported_not_fatal(window, tmp_path):
    window.show_docs()
    docs = window.docs
    assert docs.load(tmp_path / "nao_existe.md") is False
    assert docs.anchors == ["erro"]
    assert docs.load(docs.home) is True


def test_edited_documentation_is_read_again(window, tmp_path):
    copy = tmp_path / "doc.md"
    copy.write_text("# Um\n\ntexto\n", encoding="utf-8")
    window.show_docs()
    docs = window.docs
    docs.load(copy)
    assert docs.reload_if_changed() is False

    copy.write_text("# Um\n\n## Dois\n\ntexto novo\n", encoding="utf-8")
    import os
    os.utime(copy, (time.time() + 5, time.time() + 5))
    assert docs.reload_if_changed() is True
    assert docs.anchors == ["um", "dois"]
    docs.load(docs.home)


def test_sidebar_tightens_up_in_a_short_window(window):
    """Regressao: num ecra baixo o botao de correr tapava a ultima entrada."""
    before = window.geometry()
    try:
        window.geometry("1280x640+0+0")
        window.update()
        window.update()
        assert window._sidebar_compact is True
        last_entry = window.docs_link
        bottom = last_entry.winfo_rooty() + last_entry.winfo_height()
        assert bottom <= window.btn_run.winfo_rooty()        # sem sobreposicao

        window.geometry("1280x960+0+0")
        window.update()
        window.update()
        assert window._sidebar_compact is False
    finally:
        window.geometry(before)
        window.update()


# --------------------------------------------------------------------- #
#  Tema: fundos claros, texto escuro, azul e vermelho da marca
# --------------------------------------------------------------------- #
def _luminance(colour: str) -> float:
    """Luminancia relativa (WCAG) de ``#RRGGBB``."""
    channels = []
    for i in (1, 3, 5):
        c = int(colour[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_backgrounds_are_light_and_text_is_dark():
    for name in ("BG", "BG_PANEL", "BG_HEADER", "NAV_BG", "STATUS_BG",
                 "SHEET_BG", "FIELD_BG", "TILE_BG", "TAB_BG", "LOG_BG"):
        assert _luminance(getattr(C, name)) > 0.70, name
    for name in ("TEXT", "FIELD_FG", "SHEET_FG", "NAV_FG", "LOG_FG"):
        assert _luminance(getattr(C, name)) < 0.02, name


def test_text_is_readable_on_its_background():
    """Contraste minimo de 4.5:1 (WCAG AA) nas combinacoes que a janela usa."""
    for fg, bg in (("TEXT", "BG_PANEL"), ("TEXT_DIM", "BG_PANEL"),
                   ("TEXT_DIM", "BG"), ("TITLE", "BG"), ("NAV_FG", "NAV_BG"),
                   ("NAV_GROUP", "NAV_BG"), ("NAV_ACTIVE_FG", "NAV_ACTIVE_BG"),
                   ("TAB_FG", "TAB_BG"), ("BTN_FG", "BTN_BG"),
                   ("GHOST_FG", "GHOST_BG"), ("RUN_FG", "RUN_BG"),
                   ("SELECT_FG", "SELECT_BG"), ("SHEET_DIM", "SHEET_BG"),
                   ("LOG_ERR", "LOG_BG"), ("LOG_OK", "LOG_BG"),
                   ("TITLE", "HEAD_BG"), ("TEXT", "ERROR_FIELD"),
                   ("BLUE", "SHEET_BG")):
        ratio = _contrast(getattr(C, fg), getattr(C, bg))
        assert ratio >= 4.5, f"{fg} sobre {bg}: {ratio:.2f}:1"


def test_details_use_the_colours_of_the_logo():
    assert (C.NAVY, C.RED) == ("#00275D", "#BC1020")
    assert C.TITLE == C.RUN_BG == C.SELECT_BG == C.NAVY     # azul: titulos e accoes
    assert C.ACCENT == C.FLAG == C.LOG_ERR == C.RED         # vermelho: marcas e erros
