"""Piloto determinístico e sem carregamento de modelos reais."""

from __future__ import annotations

from atlas.core.lazy import LazyComponent, LazyComponentRegistry, LazyProxy


class DemoBrain:
    def respond(self, text: str) -> str:
        return f"Resposta simulada para: {text}"


class DemoVision:
    pass


def main() -> None:
    brain_component = LazyComponent("brain", DemoBrain)
    vision_component = LazyComponent("vision", DemoVision)
    registry = LazyComponentRegistry((brain_component, vision_component))
    brain = LazyProxy(brain_component)

    print("Sprint 25 — Etapa 3: lazy loading")
    print("Antes: " + ", ".join(f"{s.name}={s.state.value}" for s in registry.snapshots()))
    print(brain.respond("teste local"))
    print("Depois: " + ", ".join(f"{s.name}={s.state.value}" for s in registry.snapshots()))
    print("Brain foi carregado uma vez; Vision permaneceu descarregado.")
    print("Nenhum modelo, captura ou configuração real foi acessado.")


if __name__ == "__main__":
    main()
