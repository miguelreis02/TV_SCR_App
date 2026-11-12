"""
Testes da interface: construcao da janela, recolha e validacao dos inputs.

Nao testam o calculo (isso e o resto da suite) -- testam que a janela monta o
:class:`tvscr.RunScenario` certo a partir do formulario, e que rejeita valores
invalidos com uma mensagem que identifica o campo.

Sao automaticamente ignorados onde nao haja tkinter ou ecra disponivel.
"""

from __future__ import annotations

import sys
import json
import types
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

tk = pytest.importorskip("tkinter")

from tvscr import (KineticParameters, KineticTuning, RunScenario,   # noqa: E402
                   VolumeSweepOptions)
from tvscr_ui.main_window import MainWindow                       # noqa: E402
from tvscr_ui.widgets import FieldError                           # noqa: E402

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
