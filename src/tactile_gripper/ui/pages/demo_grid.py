"""Standalone synthetic 6×6 preview for the simulation Dashboard."""

from nicegui import ui

from ...constants import SOFTWARE_VERSION
from ...devices.sensor import SimulatedSensorAdapter, default_demo_config
from ..charts import heatmap_options
from ..theme import card_header, notice, shell


def demo_grid_page(core) -> None:
    config = default_demo_config(core.config_root)
    sensor = SimulatedSensorAdapter(config, period_s=0)
    sensor.connect()
    sensor.read_frame()  # synthetic HELLO

    def options():
        frame = sensor.read_frame()
        chart_options = heatmap_options(frame.to_dict(), config)
        chart_options["series"][0]["name"] = "合成格值"
        return chart_options, frame

    initial, frame = options()
    with shell("demo-6x6", "6×6 热力图演示", "合成格值 · 视觉演示", core, SOFTWARE_VERSION) as refs:
        refs["sensor"].set_text("合成格值")
        notice("SIMULATION ONLY · 36 个独立合成格值 · 与真实 12 电极采集和执行器隔离", "amber")
        with ui.card().classes("card w-full").style("max-width:1050px"):
            with card_header("36 格仿真热力图", "格值由仿真生成，单位为模拟计数。"):
                frame_label = ui.label(f"帧 {frame.frame_seq} · {frame.valid_channel_count}/36 格有值").classes("card-sub")

                def advance() -> None:
                    updated, sample = options()
                    chart.options.update(updated)
                    chart.update()
                    frame_label.set_text(f"帧 {sample.frame_seq} · {sample.valid_channel_count}/36 格有值")

                ui.button("下一仿真帧", on_click=advance).props("outline no-caps")
            chart = ui.echart(initial).classes("w-full").style("height:clamp(420px, 65vh, 610px)")
