"""Integration tests for GitHub Actions workflow validation.

These tests validate the structure and configuration of workflow YAML files
without requiring actual GitHub Actions execution.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


WORKFLOWS_DIR = Path(__file__).parent.parent.parent / ".github" / "workflows"
DAILY_DIGEST_WORKFLOW = WORKFLOWS_DIR / "daily-digest.yaml"
BACKFILL_RANGE_WORKFLOW = WORKFLOWS_DIR / "backfill-date-range.yaml"
RESET_SITE_WORKFLOW = WORKFLOWS_DIR / "reset-site.yaml"
LINT_WORKFLOW = WORKFLOWS_DIR / "lint-workflow.yaml"


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file."""
    with open(path, encoding="utf-8") as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def assert_vue_build_publishes_spa_route_fallbacks(run_script: str) -> None:
    """Verify Vue build output replaces legacy static route entrypoints."""
    assert 'rm -rf "../${OUTPUT_DIR}/assets"' in run_script
    assert "for ROUTE in archive sources status reports;" in run_script
    assert 'cp dist/index.html "../${OUTPUT_DIR}/${ROUTE}.html"' in run_script
    assert 'cp dist/index.html "../${OUTPUT_DIR}/${ROUTE}/index.html"' in run_script


def assert_prepare_creates_empty_report_index(run_script: str) -> None:
    """Verify report routes have a non-404 empty index fallback."""
    assert '"${OUTPUT_DIR}/api/reports/index.json"' in run_script
    assert '"weekly": []' in run_script
    assert '"monthly": []' in run_script


def assert_prepare_publishes_state_sqlite(run_script: str) -> None:
    """Verify Pages receives the real SQLite state database."""
    assert 'cp "${STATE_FILE}" "${OUTPUT_DIR}/api/state.sqlite"' in run_script


def assert_persist_state_avoids_lfs(run_script: str) -> None:
    """Verify state branch keeps SQLite as a normal Git blob for Pages restores."""
    assert "git lfs" not in run_script
    assert "git-lfs" not in run_script
    assert "rm -f .gitattributes" in run_script
    assert 'cp "../artifacts/${STATE_FILE}" api/state.sqlite' in run_script


class TestDailyDigestWorkflow:
    """Tests for the daily-digest.yaml workflow."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        """Load the daily digest workflow."""
        if not DAILY_DIGEST_WORKFLOW.exists():
            pytest.skip("daily-digest.yaml not found")
        return load_workflow(DAILY_DIGEST_WORKFLOW)

    def test_workflow_name(self, workflow: dict[str, Any]) -> None:
        """Verify workflow has a descriptive name."""
        assert "name" in workflow
        assert workflow["name"] == "Daily Digest"

    def test_schedule_and_workflow_dispatch_triggers(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify workflow supports both scheduled CI and manual reruns."""
        assert "on" in workflow
        triggers = workflow["on"]
        assert set(triggers.keys()) == {"schedule", "workflow_dispatch"}
        assert "schedule" in triggers
        assert "workflow_dispatch" in triggers
        assert triggers["schedule"][0]["cron"] == "0 6 * * *"

    def test_dispatch_inputs(self, workflow: dict[str, Any]) -> None:
        """Verify manual dispatch supports reruns and report forcing."""
        dispatch = workflow["on"]["workflow_dispatch"]
        inputs = dispatch.get("inputs", {})
        assert "target_date" in inputs
        assert inputs["target_date"].get("required") is False
        assert "deploy_only" in inputs
        assert "report_mode" in inputs
        assert inputs["report_mode"].get("default") == "auto"
        assert set(inputs["report_mode"].get("options", [])) == {
            "auto",
            "none",
            "weekly",
            "monthly",
            "all",
        }

    def test_required_permissions(self, workflow: dict[str, Any]) -> None:
        """Verify workflow has required permissions (least privilege)."""
        assert "permissions" in workflow
        permissions = workflow["permissions"]

        # Required permissions
        assert permissions.get("contents") == "write", (
            "Need contents:write for state branch"
        )
        assert permissions.get("pages") == "write", "Need pages:write for deployment"
        assert permissions.get("id-token") == "write", "Need id-token:write for OIDC"

    def test_concurrency_configuration(self, workflow: dict[str, Any]) -> None:
        """Verify concurrency is configured to prevent overlapping runs."""
        assert "concurrency" in workflow
        concurrency = workflow["concurrency"]

        # Should have a group
        assert "group" in concurrency
        assert "digest" in concurrency["group"].lower()

        # Should not cancel in progress (serialize instead)
        assert concurrency.get("cancel-in-progress") is False

    def test_environment_variables(self, workflow: dict[str, Any]) -> None:
        """Verify required environment variables are set."""
        assert "env" in workflow
        env = workflow["env"]

        required_vars = ["PYTHON_VERSION", "STATE_BRANCH", "STATE_FILE", "OUTPUT_DIR"]
        for var in required_vars:
            assert var in env, f"Missing environment variable: {var}"

    def test_jobs_structure(self, workflow: dict[str, Any]) -> None:
        """Verify workflow has required jobs."""
        assert "jobs" in workflow
        jobs = workflow["jobs"]

        # Required jobs
        required_jobs = ["digest", "deploy-pages", "persist-state"]
        for job in required_jobs:
            assert job in jobs, f"Missing job: {job}"

    def test_digest_job_steps(self, workflow: dict[str, Any]) -> None:
        """Verify digest job has daily, backfill, and report steps."""
        jobs = workflow["jobs"]
        digest_job = jobs["digest"]

        assert "steps" in digest_job
        steps = digest_job["steps"]

        # Check for key step names/ids
        step_names = []
        step_ids = []
        for step in steps:
            if "name" in step:
                step_names.append(step["name"].lower())
            if "id" in step:
                step_ids.append(step["id"])

        # Required steps
        assert any("checkout" in name for name in step_names), "Missing checkout step"
        assert any("state" in name for name in step_names), "Missing state restore step"
        assert any("python" in name for name in step_names), "Missing Python setup step"
        assert any("resolve target date" in name for name in step_names), (
            "Missing target-date resolution step"
        )
        assert any("rerun target date" in name for name in step_names), (
            "Missing backfill rerun step"
        )
        assert any("today's digest pipeline" in name for name in step_names), (
            "Missing full daily pipeline step"
        )
        assert any("generate scheduled reports" in name for name in step_names), (
            "Missing scheduled report generation step"
        )

    def test_backfill_step_uses_single_day_mode(self, workflow: dict[str, Any]) -> None:
        """Verify rerun command only executes backfill for one date."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        rerun_steps = [s for s in digest_steps if s.get("id") == "backfill"]
        assert len(rerun_steps) == 1
        run_script = rerun_steps[0].get("run", "")

        assert "main.py backfill" in run_script
        assert "--date" in run_script
        assert "--overwrite-existing" in run_script
        assert "main.py run" not in run_script

    def test_daily_run_step_uses_resolved_target_date(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify normal daily runs render the date resolved by the workflow."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        run_steps = [s for s in digest_steps if s.get("id") == "run-digest"]
        assert len(run_steps) == 1
        run_script = run_steps[0].get("run", "")

        assert "main.py run" in run_script
        assert "TARGET_DATE=" in run_script
        assert "--date" in run_script
        assert '"${TARGET_DATE}"' in run_script

    def test_report_step_generates_weekly_and_monthly_outputs(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify scheduled reports are generated from saved archives."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        report_steps = [s for s in digest_steps if s.get("id") == "generate-reports"]
        assert len(report_steps) == 1
        run_script = report_steps[0].get("run", "")

        assert "main.py report" in run_script
        assert "--type weekly" in run_script
        assert "--type monthly" in run_script
        assert "--previous-month" in run_script
        assert "--limit 100" in run_script
        assert "--archive-lookahead-days 1" in run_script

    def test_restore_state_recursively_restores_archives(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify nested archive files are restored from the state branch."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        restore_steps = [s for s in digest_steps if s.get("id") == "restore-state"]
        assert len(restore_steps) == 1
        run_script = restore_steps[0].get("run", "")

        assert 'git ls-tree -r --name-only "${STATE_BRANCH}" day/' in run_script
        assert 'git ls-tree -r --name-only "${STATE_BRANCH}" api/day/' in run_script

    def test_deploy_only_prepare_allows_restored_daily_without_target_archive(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify deploy-only report reruns are not blocked by target archive gaps."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        prepare_steps = [
            s for s in digest_steps if s.get("name") == "Prepare archive output"
        ]
        assert len(prepare_steps) == 1
        run_script = prepare_steps[0].get("run", "")

        assert 'RUN_MODE="${{ steps.validate-date.outputs.run_mode }}"' in run_script
        assert '[ "${RUN_MODE}" = "deploy-only" ]' in run_script
        assert (
            "Skipping target-date archive check for deploy-only restore" in run_script
        )

    def test_prepare_archive_output_creates_empty_report_index(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify report list page does not depend on a 404 empty state."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        prepare_steps = [
            s for s in digest_steps if s.get("name") == "Prepare archive output"
        ]
        assert len(prepare_steps) == 1

        assert_prepare_creates_empty_report_index(prepare_steps[0].get("run", ""))
        assert_prepare_publishes_state_sqlite(prepare_steps[0].get("run", ""))

    def test_report_artifacts_are_uploaded(self, workflow: dict[str, Any]) -> None:
        """Verify report JSON and SPA route artifacts are persisted."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        artifact_names = [
            step.get("with", {}).get("name")
            for step in digest_steps
            if "uses" in step and "upload-artifact" in str(step.get("uses", ""))
        ]

        assert "report-archives-json" in artifact_names
        assert "report-archives-html" in artifact_names

    def test_vue_build_replaces_legacy_static_entrypoints(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify Pages artifact cannot keep old Jinja route pages."""
        digest_steps = workflow["jobs"]["digest"]["steps"]
        build_steps = [
            s for s in digest_steps if s.get("name") == "Build Vue.js frontend"
        ]
        assert len(build_steps) == 1

        assert_vue_build_publishes_spa_route_fallbacks(build_steps[0].get("run", ""))

    def test_deploy_pages_job_depends_on_digest(self, workflow: dict[str, Any]) -> None:
        """Verify deploy-pages job depends on successful digest."""
        jobs = workflow["jobs"]
        deploy_job = jobs["deploy-pages"]

        assert "needs" in deploy_job
        assert "digest" in deploy_job["needs"]

        # Should only run if digest succeeds
        assert deploy_job.get("if") == "success()" or "success()" in str(
            deploy_job.get("if", "")
        )

    def test_persist_state_job_depends_on_digest(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify persist-state job depends on successful digest."""
        jobs = workflow["jobs"]
        persist_job = jobs["persist-state"]

        assert "needs" in persist_job
        assert "digest" in persist_job["needs"]

        # Should only run if digest succeeds
        assert persist_job.get("if") == "success()" or "success()" in str(
            persist_job.get("if", "")
        )

    def test_no_secrets_in_commands(self, workflow: dict[str, Any]) -> None:
        """Verify no secrets are directly embedded in commands."""
        workflow_text = yaml.dump(workflow)

        # Should not contain set -x (could leak secrets in logs)
        assert "set -x" not in workflow_text, "Found 'set -x' which could leak secrets"

        # Check that secrets are properly referenced via ${{ secrets.* }}
        # and not hardcoded with actual values
        # The pattern "HF_TOKEN: ${{ secrets.HF_TOKEN }}" is acceptable
        import re

        # Look for secret-like patterns that are hardcoded (not via ${{ secrets.* }})
        # Bad pattern: HF_TOKEN: "actual_token_value" or HF_TOKEN: sk-xxx
        hardcoded_pattern = re.compile(
            r"(HF_TOKEN|OPENREVIEW_TOKEN):\s*['\"]?[a-zA-Z0-9_-]{10,}['\"]?"
        )
        matches = hardcoded_pattern.findall(workflow_text)
        # Filter out valid secret references
        for match in matches:
            if f"secrets.{match}" not in workflow_text:
                raise AssertionError(f"Potential hardcoded secret: {match}")

    def test_digest_job_has_no_unused_outputs(self, workflow: dict[str, Any]) -> None:
        """Verify digest job keeps state in artifacts, not job outputs."""
        jobs = workflow["jobs"]
        digest_job = jobs["digest"]
        assert "outputs" not in digest_job

    def test_state_artifact_upload(self, workflow: dict[str, Any]) -> None:
        """Verify digest job uploads state.sqlite as artifact."""
        jobs = workflow["jobs"]
        digest_job = jobs["digest"]
        steps = digest_job["steps"]

        # Find artifact upload step
        artifact_steps = [
            s
            for s in steps
            if "uses" in s and "upload-artifact" in str(s.get("uses", ""))
        ]

        assert len(artifact_steps) >= 1, "Missing artifact upload step"

        # Verify it uploads state-sqlite
        upload_step = artifact_steps[0]
        assert "with" in upload_step
        assert upload_step["with"].get("name") == "state-sqlite"

    def test_persist_state_downloads_artifact(self, workflow: dict[str, Any]) -> None:
        """Verify persist-state job downloads artifact instead of re-running pipeline."""
        jobs = workflow["jobs"]
        persist_job = jobs["persist-state"]
        steps = persist_job["steps"]

        # Find artifact download step
        download_steps = [
            s
            for s in steps
            if "uses" in s and "download-artifact" in str(s.get("uses", ""))
        ]

        assert len(download_steps) >= 1, "Missing artifact download step"

        # Verify no pipeline re-run (no uv run python main.py run)
        for step in steps:
            if "run" in step:
                run_content = step["run"]
                assert "main.py run" not in run_content, (
                    "persist-state should not re-run pipeline"
                )

    def test_persist_state_no_secrets_needed(self, workflow: dict[str, Any]) -> None:
        """Verify persist-state job does not require API secrets."""
        jobs = workflow["jobs"]
        persist_job = jobs["persist-state"]
        steps = persist_job["steps"]

        # Check no step has HF_TOKEN or OPENREVIEW_TOKEN env
        for step in steps:
            if "env" in step:
                env = step["env"]
                assert "HF_TOKEN" not in env, "persist-state should not need HF_TOKEN"
                assert "OPENREVIEW_TOKEN" not in env, (
                    "persist-state should not need OPENREVIEW_TOKEN"
                )

    def test_persist_state_stores_sqlite_without_lfs(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify persisted SQLite remains usable by GitHub Pages artifacts."""
        steps = workflow["jobs"]["persist-state"]["steps"]
        push_steps = [s for s in steps if s.get("name") == "Push state and archives"]
        assert len(push_steps) == 1

        assert_persist_state_avoids_lfs(push_steps[0].get("run", ""))


class TestResetSiteWorkflow:
    """Tests for the reset-site.yaml workflow."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        """Load the reset-site workflow."""
        if not RESET_SITE_WORKFLOW.exists():
            pytest.skip("reset-site.yaml not found")
        return load_workflow(RESET_SITE_WORKFLOW)

    def test_only_workflow_dispatch_trigger(self, workflow: dict[str, Any]) -> None:
        """Verify reset workflow is manual-only."""
        assert "on" in workflow
        triggers = workflow["on"]
        assert set(triggers.keys()) == {"workflow_dispatch"}

    def test_dispatch_requires_confirmation(self, workflow: dict[str, Any]) -> None:
        """Verify reset requires explicit confirmation input."""
        dispatch = workflow["on"]["workflow_dispatch"]
        inputs = dispatch.get("inputs", {})
        assert set(inputs.keys()) == {"confirm_reset"}
        assert inputs["confirm_reset"].get("required") is True

    def test_jobs_structure(self, workflow: dict[str, Any]) -> None:
        """Verify reset has validation, delete, deploy, and report jobs."""
        jobs = workflow.get("jobs", {})
        required_jobs = ["validate", "delete-state", "deploy-empty", "report"]
        for job in required_jobs:
            assert job in jobs, f"Missing job: {job}"

    def test_reset_does_not_run_digest_pipeline(self, workflow: dict[str, Any]) -> None:
        """Verify reset does not execute digest/backfill commands."""
        workflow_text = yaml.dump(workflow)
        assert "main.py run" not in workflow_text
        assert "main.py backfill" not in workflow_text

    def test_reset_empty_site_publishes_spa_route_fallbacks(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify reset artifact keeps all primary routes on the Vue frontend."""
        deploy_steps = workflow["jobs"]["deploy-empty"]["steps"]
        prepare_steps = [
            s for s in deploy_steps if s.get("name") == "Prepare empty site payload"
        ]
        assert len(prepare_steps) == 1
        run_script = prepare_steps[0].get("run", "")

        assert "for ROUTE in archive sources status reports;" in run_script
        assert 'cp frontend/dist/index.html "${OUTPUT_DIR}/${ROUTE}.html"' in run_script
        assert (
            'cp frontend/dist/index.html "${OUTPUT_DIR}/${ROUTE}/index.html"'
            in run_script
        )
        assert '"${OUTPUT_DIR}/api/reports/index.json"' in run_script
        assert '"weekly": []' in run_script
        assert '"monthly": []' in run_script


class TestBackfillDateRangeWorkflow:
    """Tests for the backfill-date-range.yaml workflow."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        """Load the backfill date range workflow."""
        if not BACKFILL_RANGE_WORKFLOW.exists():
            pytest.skip("backfill-date-range.yaml not found")
        return load_workflow(BACKFILL_RANGE_WORKFLOW)

    def test_vue_build_replaces_legacy_static_entrypoints(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify range backfills publish the Vue frontend for all routes."""
        steps = workflow["jobs"]["backfill-range"]["steps"]
        build_steps = [s for s in steps if s.get("name") == "Build Vue.js frontend"]
        assert len(build_steps) == 1

        assert_vue_build_publishes_spa_route_fallbacks(build_steps[0].get("run", ""))

    def test_prepare_archive_output_creates_empty_report_index(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify range backfill report route has a non-404 empty index."""
        steps = workflow["jobs"]["backfill-range"]["steps"]
        prepare_steps = [s for s in steps if s.get("name") == "Prepare archive output"]
        assert len(prepare_steps) == 1

        assert_prepare_creates_empty_report_index(prepare_steps[0].get("run", ""))
        assert_prepare_publishes_state_sqlite(prepare_steps[0].get("run", ""))

    def test_persist_state_stores_sqlite_without_lfs(
        self, workflow: dict[str, Any]
    ) -> None:
        """Verify range backfill persists a browser-fetchable SQLite file."""
        steps = workflow["jobs"]["persist-state"]["steps"]
        push_steps = [s for s in steps if s.get("name") == "Push state and archives"]
        assert len(push_steps) == 1

        assert_persist_state_avoids_lfs(push_steps[0].get("run", ""))


class TestLintWorkflow:
    """Tests for the lint-workflow.yaml workflow."""

    @pytest.fixture
    def workflow(self) -> dict[str, Any]:
        """Load the lint workflow."""
        if not LINT_WORKFLOW.exists():
            pytest.skip("lint-workflow.yaml not found")
        return load_workflow(LINT_WORKFLOW)

    def test_workflow_name(self, workflow: dict[str, Any]) -> None:
        """Verify workflow has a descriptive name."""
        assert "name" in workflow
        assert "lint" in workflow["name"].lower()

    def test_triggers_on_workflow_changes(self, workflow: dict[str, Any]) -> None:
        """Verify workflow triggers on changes to workflow files."""
        triggers = workflow["on"]

        # Should trigger on push and pull_request to workflow paths
        for trigger_type in ["push", "pull_request"]:
            assert trigger_type in triggers
            trigger = triggers[trigger_type]
            assert "paths" in trigger
            paths = trigger["paths"]
            assert any(".github/workflows" in str(p) for p in paths)

    def test_read_only_permissions(self, workflow: dict[str, Any]) -> None:
        """Verify lint workflow only has read permissions."""
        assert "permissions" in workflow
        permissions = workflow["permissions"]

        # Should only have contents:read
        assert permissions.get("contents") == "read"


class TestWorkflowFilesExist:
    """Tests to verify required workflow files exist."""

    def test_workflows_directory_exists(self) -> None:
        """Verify .github/workflows directory exists."""
        assert WORKFLOWS_DIR.exists(), f"Workflows directory not found: {WORKFLOWS_DIR}"

    def test_daily_digest_workflow_exists(self) -> None:
        """Verify daily-digest.yaml exists."""
        assert DAILY_DIGEST_WORKFLOW.exists(), (
            f"Workflow not found: {DAILY_DIGEST_WORKFLOW}"
        )

    def test_reset_site_workflow_exists(self) -> None:
        """Verify reset-site.yaml exists."""
        assert RESET_SITE_WORKFLOW.exists(), (
            f"Workflow not found: {RESET_SITE_WORKFLOW}"
        )

    def test_lint_workflow_exists(self) -> None:
        """Verify lint-workflow.yaml exists."""
        assert LINT_WORKFLOW.exists(), f"Workflow not found: {LINT_WORKFLOW}"

    def test_workflow_files_are_valid_yaml(self) -> None:
        """Verify all workflow files are valid YAML."""
        for workflow_file in WORKFLOWS_DIR.glob("*.yaml"):
            try:
                load_workflow(workflow_file)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in {workflow_file}: {e}")

        for workflow_file in WORKFLOWS_DIR.glob("*.yml"):
            try:
                load_workflow(workflow_file)
            except yaml.YAMLError as e:
                pytest.fail(f"Invalid YAML in {workflow_file}: {e}")


class TestTemplateFiles:
    """Tests to verify template files follow best practices."""

    TEMPLATES_DIR = (
        Path(__file__).parent.parent.parent / "src" / "renderer" / "templates"
    )

    def test_macros_file_exists(self) -> None:
        """Verify _macros.html exists for DRY template patterns."""
        macros_file = self.TEMPLATES_DIR / "_macros.html"
        assert macros_file.exists(), f"Macros file not found: {macros_file}"

    def test_base_template_has_skip_link(self) -> None:
        """Verify base.html has skip-to-content link for accessibility."""
        base_file = self.TEMPLATES_DIR / "base.html"
        assert base_file.exists()

        content = base_file.read_text()
        assert "skip-link" in content, "Missing skip-link for accessibility"
        assert "#main-content" in content, "Missing main-content anchor"

    def test_base_template_has_aria_current(self) -> None:
        """Verify base.html uses aria-current for current page indicator."""
        base_file = self.TEMPLATES_DIR / "base.html"
        assert base_file.exists()

        content = base_file.read_text()
        assert 'aria-current="page"' in content, "Missing aria-current for nav"

    def test_templates_import_macros(self) -> None:
        """Verify index.html and day.html import and use macros."""
        for template_name in ["index.html", "day.html"]:
            template_file = self.TEMPLATES_DIR / template_name
            assert template_file.exists()

            content = template_file.read_text()
            assert 'from "_macros.html" import' in content, (
                f"{template_name} should import macros"
            )
            assert "story_card" in content, (
                f"{template_name} should use story_card macro"
            )
