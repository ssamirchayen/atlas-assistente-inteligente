"""Offline commands: python -m atlas.radiology demo|validate."""

import argparse
import json
from pathlib import Path

from atlas.radiology.cases import CaseError, validate_case
from atlas.radiology.demo import create_demo


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Atlas Radiologia — fundação experimental RX 3D"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser(
        "demo", help="Criar padrões sintéticos, sem imagens médicas"
    )
    demo.add_argument("--output", type=Path, required=True)
    demo2d = commands.add_parser(
        "demo2d", help="Criar laboratório PNG/JPEG/DICOM com visualizador"
    )
    demo2d.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser(
        "validate", help="Conferir manifesto e integridade dos arquivos"
    )
    validate.add_argument("manifest", type=Path)
    inspect = commands.add_parser(
        "inspect", help="Decodificar uma imagem e conferir metadados técnicos"
    )
    inspect.add_argument("image", type=Path)
    importer = commands.add_parser(
        "import", help="Importar três imagens para um novo caso"
    )
    for name in ("ap", "lateral", "oblique"):
        importer.add_argument("--" + name, type=Path, required=True)
    importer.add_argument("--side", choices=("L", "R"), required=True)
    importer.add_argument(
        "--origin", choices=("synthetic", "research"), default="research"
    )
    importer.add_argument("--output", type=Path, required=True)
    viewer = commands.add_parser("viewer", help="Gerar visualizador HTML local")
    viewer.add_argument("manifest", type=Path)
    viewer.add_argument("--output", type=Path, required=True)
    privacy = commands.add_parser("privacy-prepare", help="Preparar cópias para revisão")
    privacy.add_argument("manifest", type=Path)
    privacy.add_argument("--output", type=Path, required=True)
    privacy.add_argument("--masks", type=Path)
    review = commands.add_parser("privacy-review", help="Registrar revisão humana")
    review.add_argument("folder", type=Path)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--output", type=Path, required=True)
    for name in ("ap", "lateral", "oblique"):
        review.add_argument("--" + name, choices=("clear", "reject"), required=True)
    export = commands.add_parser("privacy-export", help="Exportar cópias aprovadas")
    export.add_argument("folder", type=Path)
    export.add_argument("--review", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    quality = commands.add_parser("quality", help="Triagem técnica e modelo de revisão")
    quality.add_argument("manifest", type=Path)
    quality.add_argument("--output", type=Path, required=True)
    quality.add_argument("--template", type=Path, required=True)
    quality_review = commands.add_parser("quality-review", help="Conferir revisão humana")
    quality_review.add_argument("manifest", type=Path)
    quality_review.add_argument("--review", type=Path, required=True)
    quality_review.add_argument("--output", type=Path, required=True)
    geometry_demo = commands.add_parser("geometry-demo", help="Criar calibração sintética")
    geometry_demo.add_argument("--output", type=Path, required=True)
    geometry = commands.add_parser("geometry-check", help="Conferir geometria fornecida")
    geometry.add_argument("config", type=Path)
    geometry.add_argument("--manifest", type=Path)
    geometry.add_argument("--output", type=Path, required=True)
    annotation_editor = commands.add_parser("annotation-editor", help="Editor manual de contornos e marcos")
    annotation_editor.add_argument("manifest", type=Path)
    annotation_editor.add_argument("--output", type=Path, required=True)
    annotation_export = commands.add_parser("annotation-export", help="Validar anotações e gerar máscaras")
    annotation_export.add_argument("manifest", type=Path)
    annotation_export.add_argument("--annotation", type=Path, required=True)
    annotation_export.add_argument("--output", type=Path, required=True)
    reconstruction_demo = commands.add_parser("reconstruction-demo", help="LAB geométrico de volume 3D")
    reconstruction_demo.add_argument("--output", type=Path, required=True)
    reconstruction = commands.add_parser("reconstruct", help="Envelope 3D experimental por contornos")
    reconstruction.add_argument("manifest", type=Path)
    reconstruction.add_argument("--annotation", type=Path, required=True)
    reconstruction.add_argument("--geometry", type=Path, required=True)
    reconstruction.add_argument("--settings", type=Path, required=True)
    reconstruction.add_argument("--output", type=Path, required=True)
    refdemo = commands.add_parser("reference-demo", help="LAB de referência e projeções sintéticas")
    refdemo.add_argument("--output", type=Path, required=True)
    refimport = commands.add_parser("reference-import", help="Importar volume canônico autorizado")
    refimport.add_argument("volume", type=Path)
    refimport.add_argument("--subject", required=True)
    refimport.add_argument("--split", choices=("train", "validation", "test"), required=True)
    refimport.add_argument("--authorized", action="store_true")
    refimport.add_argument("--privacy-reviewed", action="store_true")
    refimport.add_argument("--output", type=Path, required=True)
    refproject = commands.add_parser("reference-project", help="Gerar projeções aproximadas do volume")
    refproject.add_argument("reference", type=Path)
    refproject.add_argument("--geometry", type=Path, required=True)
    refproject.add_argument("--step-mm", type=float, default=1.0)
    refproject.add_argument("--water-mu", type=float, default=.02)
    refproject.add_argument("--output", type=Path, required=True)
    refcompare = commands.add_parser("reference-compare", help="Comparar máscara predita e referência")
    refcompare.add_argument("reference", type=Path)
    refcompare.add_argument("--prediction", type=Path, required=True)
    refcompare.add_argument("--output", type=Path, required=True)
    refaudit = commands.add_parser("reference-audit", help="Detectar sobreposição entre divisões")
    refaudit.add_argument("references", type=Path, nargs="+")
    refaudit.add_argument("--output", type=Path, required=True)
    refadapt = commands.add_parser("reference-adapt-stage7", help="Converter volume da Etapa 7 para comparação")
    refadapt.add_argument("volume", type=Path)
    refadapt.add_argument("--output", type=Path, required=True)
    linked = commands.add_parser("linked-viewer", help="Visualizador integrado imagens e malha 3D")
    linked.add_argument("manifest", type=Path)
    linked.add_argument("--geometry", type=Path, required=True)
    linked.add_argument("--result", type=Path, required=True)
    linked.add_argument("--output", type=Path, required=True)
    linked_demo = commands.add_parser("linked-demo", help="LAB sintético com visualizador 3D integrado")
    linked_demo.add_argument("--output", type=Path, required=True)
    sensitivity = commands.add_parser("sensitivity", help="Avaliar sensibilidade aos contornos")
    sensitivity.add_argument("manifest", type=Path)
    for name in ("annotation", "geometry", "settings", "output"):
        sensitivity.add_argument("--" + name, type=Path, required=True)
    sensitivity.add_argument("--radius-px", type=int, default=1)
    sensitivity_demo = commands.add_parser("sensitivity-demo", help="LAB de sensibilidade sintética")
    sensitivity_demo.add_argument("--output", type=Path, required=True)
    bundle = commands.add_parser("export-bundle", help="Exportar pacote de pesquisa OBJ/STL")
    bundle.add_argument("manifest", type=Path)
    for name in ("annotation", "geometry", "settings", "output"):
        bundle.add_argument("--" + name, type=Path, required=True)
    bundle.add_argument("--diagnostic", action="store_true")
    bundle_demo = commands.add_parser("export-demo", help="LAB de exportação com rejeição preservada")
    bundle_demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in {"export-bundle", "export-demo"}:
            from atlas.radiology.export_bundle import export_bundle

            if args.command == "export-demo":
                from atlas.radiology.reconstruction_lab import create_reconstruction_lab

                create_reconstruction_lab(args.output)
                paths = (args.output / "case/case.json", args.output / "annotations.json",
                         args.output / "geometry.json", args.output / "reconstruction-settings.json")
                export_bundle(*paths, args.output / "blocked-export")
                report = export_bundle(*paths, args.output / "diagnostic-export", diagnostic=True)
            else:
                report = export_bundle(args.manifest, args.annotation, args.geometry,
                                       args.settings, args.output, args.diagnostic)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2 if report["reasons"] else 0
        if args.command in {"sensitivity", "sensitivity-demo"}:
            from atlas.radiology.uncertainty import assess

            if args.command == "sensitivity-demo":
                from atlas.radiology.reconstruction_lab import create_reconstruction_lab

                create_reconstruction_lab(args.output)
                report = assess(args.output / "case/case.json", args.output / "annotations.json",
                                args.output / "geometry.json", args.output / "reconstruction-settings.json",
                                args.output / "assessment")
            else:
                report = assess(args.manifest, args.annotation, args.geometry,
                                args.settings, args.output, args.radius_px)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2 if report["reasons"] else 0
        if args.command in {"linked-viewer", "linked-demo"}:
            from atlas.radiology.linked_viewer import build_linked_viewer

            if args.command == "linked-demo":
                from atlas.radiology.reconstruction_lab import create_reconstruction_lab

                create_reconstruction_lab(args.output)
                build_linked_viewer(args.output / "case/case.json",
                                    args.output / "geometry.json", args.output / "result",
                                    args.output / "linked-viewer")
            else:
                build_linked_viewer(args.manifest,args.geometry,args.result,args.output)
            print(json.dumps({"status":"linked_viewer_created","clinical_use_validated":False}))
            return 0
        if args.command.startswith("reference-"):
            from atlas.radiology.privacy import write_json
            from atlas.radiology.reference import audit_reference_splits, import_reference
            from atlas.radiology.reference_benchmark import adapt_stage7_prediction, compare_reference
            from atlas.radiology.reference_lab import create_reference_lab
            from atlas.radiology.reference_projection import create_projections

            if args.command == "reference-demo":
                create_reference_lab(args.output)
            elif args.command == "reference-import":
                import_reference(args.volume,args.output,args.subject,args.split,
                                 authorized=args.authorized,privacy_reviewed=args.privacy_reviewed)
            elif args.command == "reference-project":
                create_projections(args.reference,args.geometry,args.output,
                                   args.step_mm,args.water_mu)
            elif args.command == "reference-compare":
                compare_reference(args.reference,args.prediction,args.output)
            elif args.command == "reference-adapt-stage7":
                adapt_stage7_prediction(args.volume,args.output)
            else:
                write_json(args.output,audit_reference_splits(args.references))
            print(json.dumps({"status":"completed","clinical_use_validated":False}))
            return 0
        if args.command in {"reconstruction-demo", "reconstruct"}:
            from atlas.radiology.privacy import read_json
            from atlas.radiology.reconstruction import reconstruct
            from atlas.radiology.reconstruction_lab import create_reconstruction_lab

            if args.command == "reconstruction-demo":
                result = create_reconstruction_lab(args.output)
            else:
                result = reconstruct(args.manifest, args.annotation, args.geometry,
                                     args.settings, args.output)
            report = read_json(result)
            print(json.dumps({"status": report["status"], "clinical_use_validated": False}))
            return 2 if report["touches_roi_boundary"] else 0
        if args.command in {"annotation-editor", "annotation-export"}:
            from atlas.radiology.annotations import create_annotation_editor, export_annotation

            if args.command == "annotation-editor":
                create_annotation_editor(args.manifest, args.output)
                status = "manual_editor_created"
            else:
                export_annotation(args.manifest, args.annotation, args.output)
                status = "manual_annotations_exported"
            print(json.dumps({"status": status, "clinical_use_validated": False}))
            return 0
        if args.command in {"geometry-demo", "geometry-check"}:
            from atlas.radiology.geometry import create_geometry_demo, validate_geometry
            from atlas.radiology.privacy import write_json

            if args.command == "geometry-demo":
                create_geometry_demo(args.output)
                print(json.dumps({"status": "synthetic_geometry_created"}))
                return 0
            report = validate_geometry(args.config, args.manifest)
            write_json(args.output, report)
            print(json.dumps({"status": report["status"],
                              "physical_calibration_verified": False}))
            return 2 if report["status"] == "blocked" else 0
        if args.command in {"quality", "quality-review"}:
            from atlas.radiology.quality import (
                analyze_quality, review_quality, write_review_template,
            )
            from atlas.radiology.privacy import write_json

            if args.command == "quality":
                from atlas.radiology.cases import require

                require(args.output.resolve() != args.template.resolve()
                        and not args.output.exists() and not args.template.exists(),
                        "output_exists", "Escolha dois arquivos novos e diferentes.")
                report = analyze_quality(args.manifest)
                write_json(args.output, report)
                write_review_template(report, args.template)
            else:
                report = review_quality(args.manifest, args.review, args.output)
            print(json.dumps({"status": report["status"],
                              "clinical_use_validated": False}))
            return 2 if report["status"] == "blocked" else 0
        if args.command.startswith("privacy-"):
            from atlas.radiology.privacy import (
                export_reviewed, prepare_privacy, read_json, record_review,
            )

            if args.command == "privacy-prepare":
                prepare_privacy(args.manifest, args.output,
                                read_json(args.masks) if args.masks else None)
                status = "pending_pixel_review"
            elif args.command == "privacy-review":
                record_review(args.folder,
                              {"AP": args.ap, "LATERAL": args.lateral,
                               "OBLIQUE": args.oblique}, args.reviewer, args.output)
                status = "review_recorded"
            else:
                export_reviewed(args.folder, args.review, args.output)
                status = "human_reviewed_display_derivatives"
            print(json.dumps({"status": status, "clinical_use_validated": False}))
            return 0
        if args.command == "demo2d":
            from atlas.radiology.lab import create_demo_2d

            create_demo_2d(args.output)
            print(
                json.dumps(
                    {
                        "status": "synthetic_2d_lab_created",
                        "viewer": "viewer/index.html",
                        "reconstruction_available": False,
                    },
                    indent=2,
                )
            )
            return 0
        if args.command == "inspect":
            from atlas.radiology.imaging import decode_image, read_image_bytes

            result = decode_image(read_image_bytes(args.image), args.image.suffix)
            print(json.dumps(result.metadata, ensure_ascii=False, indent=2))
            return 0
        if args.command in {"import", "viewer"}:
            from atlas.radiology.workspace import build_viewer, import_case

            if args.command == "import":
                manifest = import_case(
                    {"AP": args.ap, "LATERAL": args.lateral, "OBLIQUE": args.oblique},
                    args.output,
                    args.side,
                    args.origin,
                )
                print(
                    json.dumps(
                        {**validate_case(manifest), "pixel_decoding_performed": True},
                        indent=2,
                    )
                )
            else:
                build_viewer(args.manifest, args.output)
                print(
                    json.dumps(
                        {
                            "status": "viewer_created",
                            "pixel_decoding_performed": True,
                            "reconstruction_available": False,
                        },
                        indent=2,
                    )
                )
            return 0
        manifest = create_demo(args.output) if args.command == "demo" else args.manifest
        print(json.dumps(validate_case(manifest), ensure_ascii=False, indent=2))
        return 0
    except CaseError as exc:
        print(
            json.dumps(
                {"status": "rejected", "code": exc.code, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1
    except OSError:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": "output_unavailable",
                    "message": "Use uma pasta nova e gravável para o caso sintético.",
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
