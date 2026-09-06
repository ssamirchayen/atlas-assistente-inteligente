"""PySide6 mini frontend for Atlas Benchmark & Validation Lab."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .dashboard_model import build_portfolio_payload, recent_run_cards, suite_cards
from .models import BenchmarkStatus
from .runtime import BenchmarkRuntimeOptions, execute_suite


class BenchmarkWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        project_root: Path,
        suite_id: str,
        *,
        version: str,
        seed: int,
        live: bool,
        resources: bool,
    ) -> None:
        super().__init__()
        self.project_root = project_root
        self.suite_id = suite_id
        self.version = version
        self.seed = seed
        self.live = live
        self.resources = resources

    def run(self) -> None:
        try:
            options = BenchmarkRuntimeOptions(
                live=self.live,
                resource_monitoring=self.resources,
                save_run=True,
            )
            run, path = execute_suite(
                self.project_root,
                self.suite_id,
                version=self.version or None,
                seed=self.seed,
                options=options,
            )
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(run, path)


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "—", caption: str = "") -> None:
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(5)
        title_label = QLabel(title.upper())
        title_label.setObjectName("metricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("metricCaption")
        self.caption_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

    def set_value(self, value: str, caption: str | None = None) -> None:
        self.value_label.setText(value)
        if caption is not None:
            self.caption_label.setText(caption)


class BenchmarkDashboardWindow(QMainWindow):
    """Compact operator dashboard for technical and business benchmarks."""

    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = Path(project_root).resolve()
        self._thread: QThread | None = None
        self._worker: BenchmarkWorker | None = None
        self._suites = suite_cards(self.project_root)
        self._portfolio = build_portfolio_payload(self.project_root)
        self._configure_window()
        self._build_ui()
        self._load_portfolio()
        self._refresh_history()

    def _configure_window(self) -> None:
        self.setWindowTitle("Atlas Benchmark — Nexyra Validation Lab")
        self.resize(1380, 860)
        self.setMinimumSize(1120, 720)
        self.setStyleSheet(self._stylesheet())

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_runner_bar())
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_overview_tab(), "Visão geral")
        self.tabs.addTab(self._build_business_tab(), "Impacto empresarial")
        self.tabs.addTab(self._build_results_tab(), "Resultado atual")
        self.tabs.addTab(self._build_history_tab(), "Histórico")
        layout.addWidget(self.tabs, stretch=1)
        footer = QLabel(
            "Resultados empresariais são simulações sintéticas. "
            "Benchmarks técnicos medidos são exibidos separadamente."
        )
        footer.setObjectName("footer")
        footer.setWordWrap(True)
        layout.addWidget(footer)

    def _build_header(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        identity = QVBoxLayout()
        title = QLabel("ATLAS BENCHMARK")
        title.setObjectName("brand")
        subtitle = QLabel("VALIDATION LAB  •  by NEXYRA")
        subtitle.setObjectName("brandCaption")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        row.addLayout(identity)
        row.addStretch()
        self.status_badge = QLabel("PRONTO")
        self.status_badge.setObjectName("statusBadge")
        row.addWidget(self.status_badge)
        return box

    def _build_runner_bar(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("runnerPanel")
        row = QHBoxLayout(panel)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(12)

        self.suite_combo = QComboBox()
        self.suite_combo.setMinimumWidth(360)
        for suite in self._suites:
            self.suite_combo.addItem(
                f"{suite.title}  ({suite.case_count} casos)", suite.suite_id
            )

        self.version_input = QLineEdit("1.0.0")
        self.version_input.setMaximumWidth(110)
        self.version_input.setPlaceholderText("versão")
        self.seed_input = QSpinBox()
        self.seed_input.setRange(1, 999999)
        self.seed_input.setValue(27)
        self.seed_input.setMaximumWidth(90)

        self.resource_check = QCheckBox("Recursos")
        self.resource_check.setChecked(True)
        self.live_check = QCheckBox("LIVE")
        self.live_check.setToolTip(
            "LIVE habilita probes reais. Vision pode capturar a tela atual."
        )
        self.run_button = QPushButton("EXECUTAR BENCHMARK")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self._start_run)

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(130)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        row.addWidget(QLabel("Suíte"))
        row.addWidget(self.suite_combo, stretch=1)
        row.addWidget(QLabel("Versão"))
        row.addWidget(self.version_input)
        row.addWidget(QLabel("Seed"))
        row.addWidget(self.seed_input)
        row.addWidget(self.resource_check)
        row.addWidget(self.live_check)
        row.addWidget(self.progress)
        row.addWidget(self.run_button)
        return panel

    def _build_overview_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(14)
        cards = QGridLayout()
        cards.setSpacing(12)
        self.score_card = MetricCard("Score atual", "—", "Nenhuma execução nesta sessão")
        self.success_card = MetricCard("Sucesso", "—", "Casos avaliados")
        self.pass_card = MetricCard("Passes", "—", "PASS / FAIL / ERROR")
        self.mode_card = MetricCard("Modo", "SAFE", "LIVE desativado")
        cards.addWidget(self.score_card, 0, 0)
        cards.addWidget(self.success_card, 0, 1)
        cards.addWidget(self.pass_card, 0, 2)
        cards.addWidget(self.mode_card, 0, 3)
        layout.addLayout(cards)

        self.overview_table = QTableWidget(0, 5)
        self.overview_table.setHorizontalHeaderLabels(
            ["Suíte", "Tipo", "Casos", "Etapa", "LIVE"]
        )
        self._setup_table(self.overview_table)
        self.overview_table.setRowCount(len(self._suites))
        for row, suite in enumerate(self._suites):
            values = (
                suite.title,
                suite.kind,
                str(suite.case_count),
                str(suite.stage),
                "Disponível" if suite.live_capable else "—",
            )
            for column, value in enumerate(values):
                self.overview_table.setItem(row, column, QTableWidgetItem(value))
        layout.addWidget(self.overview_table, stretch=1)
        return page

    def _build_business_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(14)

        tag = QLabel("SIMULAÇÃO SINTÉTICA — NÃO É GARANTIA COMERCIAL")
        tag.setObjectName("simulationTag")
        layout.addWidget(tag)

        cards = QGridLayout()
        cards.setSpacing(12)
        self.hours_card = MetricCard("Horas liberadas", "—", "por mês")
        self.reduction_card = MetricCard("Redução humana", "—", "trabalho repetitivo")
        self.throughput_card = MetricCard("Capacidade", "—", "ganho de throughput")
        self.value_card = MetricCard("Capacidade potencial", "—", "projeção mensal")
        cards.addWidget(self.hours_card, 0, 0)
        cards.addWidget(self.reduction_card, 0, 1)
        cards.addWidget(self.throughput_card, 0, 2)
        cards.addWidget(self.value_card, 0, 3)
        layout.addLayout(cards)

        self.business_table = QTableWidget(0, 6)
        self.business_table.setHorizontalHeaderLabels(
            ["Lab", "Volume", "Manual h", "Atlas h", "Liberadas h", "Redução"]
        )
        self._setup_table(self.business_table)
        layout.addWidget(self.business_table, stretch=1)

        self.business_disclaimer = QLabel()
        self.business_disclaimer.setObjectName("disclaimer")
        self.business_disclaimer.setWordWrap(True)
        layout.addWidget(self.business_disclaimer)
        return page

    def _build_results_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 16, 4, 4)
        self.result_title = QLabel("Nenhum benchmark executado nesta sessão.")
        self.result_title.setObjectName("sectionTitle")
        layout.addWidget(self.result_title)
        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(
            ["Status", "Caso", "Domínio", "Duração", "Score"]
        )
        self._setup_table(self.results_table)
        layout.addWidget(self.results_table, stretch=1)
        return page

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 16, 4, 4)
        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(
            ["Suíte", "Versão", "Score", "Sucesso", "PASS", "Falhas", "LIVE"]
        )
        self._setup_table(self.history_table)
        layout.addWidget(self.history_table, stretch=1)
        return page

    @staticmethod
    def _setup_table(table: QTableWidget) -> None:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def _load_portfolio(self) -> None:
        portfolio = self._portfolio["portfolio"]
        evidence = self._portfolio["evidence"]["economic_projection"]
        self.hours_card.set_value(
            f"{portfolio['total_human_hours_liberated']:.1f} h",
            "capacidade humana liberada / período",
        )
        self.reduction_card.set_value(
            f"{portfolio['human_time_reduction_pct']:.1f}%"
        )
        self.throughput_card.set_value(
            f"+{portfolio['throughput_gain_pct']:.1f}%"
        )
        self.value_card.set_value(
            self._brl(evidence["potential_capacity_value_brl"]),
            "valor potencial — não economia garantida",
        )

        labs = self._portfolio["labs"]
        self.business_table.setRowCount(len(labs))
        for row, lab in enumerate(labs):
            simulated = lab["simulated"]
            values = (
                lab["title"],
                f"{lab['volume']:.0f}",
                f"{simulated['manual_human_hours']:.1f}",
                f"{simulated['atlas_human_hours']:.1f}",
                f"{simulated['human_hours_liberated']:.1f}",
                f"{simulated['human_time_reduction_pct']:.1f}%",
            )
            for column, value in enumerate(values):
                self.business_table.setItem(row, column, QTableWidgetItem(value))
        self.business_disclaimer.setText(str(self._portfolio["disclaimer"]))

    def _refresh_history(self) -> None:
        cards = recent_run_cards(self.project_root, limit=20)
        self.history_table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            values = (
                card.title,
                card.version,
                f"{card.weighted_score:.1f}",
                f"{card.success_rate_pct:.1f}%",
                str(card.passed),
                str(card.failed + card.errors),
                "SIM" if card.live else "NÃO",
            )
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(value))

    def _start_run(self) -> None:
        if self._thread is not None:
            return
        suite_id = str(self.suite_combo.currentData())
        live = self.live_check.isChecked()
        if live and not self._confirm_live():
            return

        self.run_button.setEnabled(False)
        self.status_badge.setText("EXECUTANDO")
        self.progress.setRange(0, 0)
        self.mode_card.set_value("LIVE" if live else "SAFE")

        self._thread = QThread(self)
        self._worker = BenchmarkWorker(
            self.project_root,
            suite_id,
            version=self.version_input.text().strip(),
            seed=self.seed_input.value(),
            live=live,
            resources=self.resource_check.isChecked(),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._run_finished)
        self._worker.failed.connect(self._run_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker)
        self._thread.start()

    def _confirm_live(self) -> bool:
        text = (
            "O modo LIVE executa probes reais. Dependendo da suíte, pode usar "
            "Ollama, Edge TTS ou capturar a tela atual para Vision local. "
            "Deseja continuar?"
        )
        answer = QMessageBox.question(
            self,
            "Executar benchmark LIVE",
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer is QMessageBox.StandardButton.Yes

    def _run_finished(self, run, path) -> None:
        summary = run.summary
        self.status_badge.setText("PASS" if not summary.failed and not summary.errors else "ATENÇÃO")
        self.progress.setRange(0, 100)
        self.progress.setValue(round(summary.success_rate))
        self.score_card.set_value(
            f"{summary.weighted_score:.1f}/100",
            run.suite_title,
        )
        self.success_card.set_value(
            f"{summary.success_rate:.1f}%",
            f"{summary.evaluated} casos avaliados",
        )
        self.pass_card.set_value(
            f"{summary.passed}/{summary.evaluated}",
            f"FAIL {summary.failed}  •  ERROR {summary.errors}  •  SKIP {summary.skipped}",
        )
        self.result_title.setText(
            f"{run.suite_title}  •  {run.atlas_version}  •  {run.run_id}"
        )
        self.results_table.setRowCount(len(run.results))
        for row, result in enumerate(run.results):
            values = (
                result.status.value,
                result.title,
                result.domain,
                f"{result.duration_ms:.1f} ms",
                f"{result.score:.1f}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_table.setItem(row, column, item)
        if any(result.status is not BenchmarkStatus.PASS for result in run.results):
            self.tabs.setCurrentWidget(self.tabs.widget(2))
        self._refresh_history()
        self.run_button.setEnabled(True)
        if path is not None:
            self.statusBar().showMessage(f"Resultado salvo em {path}", 7000)

    def _run_failed(self, message: str) -> None:
        self.status_badge.setText("ERRO")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.run_button.setEnabled(True)
        QMessageBox.critical(self, "Benchmark falhou", message)

    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None
        self.run_button.setEnabled(True)

    @staticmethod
    def _brl(value: float) -> str:
        raw = f"{float(value):,.2f}"
        return "R$ " + raw.replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _stylesheet() -> str:
        return """
        QWidget#root { background: #07111f; color: #dbeafe; }
        QWidget { font-family: 'Segoe UI'; font-size: 13px; }
        QLabel#brand { font-size: 24px; font-weight: 800; color: #f8fbff; }
        QLabel#brandCaption { color: #6384aa; font-size: 11px; font-weight: 700; }
        QLabel#statusBadge {
            background: #0b2535; color: #67e8f9; border: 1px solid #155e75;
            border-radius: 12px; padding: 7px 13px; font-weight: 800;
        }
        QFrame#runnerPanel, QFrame#metricCard {
            background: #0b1828; border: 1px solid #17324c; border-radius: 12px;
        }
        QLabel#metricTitle { color: #6f8eae; font-size: 10px; font-weight: 800; }
        QLabel#metricValue { color: #f8fbff; font-size: 25px; font-weight: 800; }
        QLabel#metricCaption { color: #7894af; font-size: 11px; }
        QLabel#simulationTag {
            color: #fbbf24; background: #2a2109; border: 1px solid #6b5311;
            border-radius: 8px; padding: 7px 10px; font-weight: 700;
        }
        QLabel#sectionTitle { color: #e8f3ff; font-size: 16px; font-weight: 700; }
        QLabel#disclaimer, QLabel#footer { color: #718aa5; font-size: 11px; }
        QPushButton#primaryButton {
            background: #0891b2; color: white; border: 0; border-radius: 8px;
            padding: 9px 16px; font-weight: 800;
        }
        QPushButton#primaryButton:hover { background: #06b6d4; }
        QPushButton#primaryButton:disabled { background: #274155; color: #7690a7; }
        QComboBox, QLineEdit, QSpinBox {
            background: #081522; color: #dbeafe; border: 1px solid #21415e;
            border-radius: 7px; padding: 7px 9px;
        }
        QTabWidget::pane { border: 1px solid #17324c; border-radius: 10px; }
        QTabBar::tab {
            background: #091727; color: #7894af; padding: 10px 18px;
            border: 1px solid #17324c;
        }
        QTabBar::tab:selected { color: #eaf7ff; background: #0c2235; }
        QTableWidget {
            background: #081522; alternate-background-color: #0a1929;
            color: #dbeafe; gridline-color: #153149; border: 1px solid #17324c;
            border-radius: 8px;
        }
        QHeaderView::section {
            background: #0d2032; color: #8aa8c4; border: 0;
            border-bottom: 1px solid #1b3c57; padding: 8px; font-weight: 700;
        }
        QProgressBar {
            background: #081522; border: 1px solid #21415e;
            border-radius: 5px; min-height: 10px;
        }
        QProgressBar::chunk { background: #06b6d4; border-radius: 4px; }
        QCheckBox { color: #abc3da; spacing: 6px; }
        QStatusBar { color: #7995af; }
        """


def run_dashboard(project_root: Path | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    root = Path(project_root or Path.cwd()).resolve()
    window = BenchmarkDashboardWindow(root)
    window.show()
    return app.exec()
