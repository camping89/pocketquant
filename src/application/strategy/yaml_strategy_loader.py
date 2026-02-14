"""YAML strategy loader for parsing strategy configuration files."""

from pathlib import Path

import structlog
import yaml

from src.domain.strategy.value_objects import StrategyConfig

logger = structlog.get_logger(__name__)


class StrategyLoaderError(Exception):
    """Raised when strategy loading fails."""


class StrategyLoader:
    """Load strategy configurations from YAML files."""

    @staticmethod
    def load(path: Path) -> StrategyConfig:
        """Load a single strategy configuration from YAML file.

        Args:
            path: Path to YAML file

        Returns:
            StrategyConfig instance

        Raises:
            StrategyLoaderError: If file cannot be read or parsed
        """
        if not path.exists():
            raise StrategyLoaderError(f"Strategy file not found: {path}")

        if path.suffix not in (".yaml", ".yml"):
            raise StrategyLoaderError(f"Invalid file type: {path.suffix}")

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                raise StrategyLoaderError(f"Empty strategy file: {path}")

            # Use filename as ID if not specified
            if "id" not in data:
                data["id"] = path.stem

            config = StrategyConfig.from_dict(data)

            # Validate configuration
            errors = config.validate()
            if errors:
                raise StrategyLoaderError(
                    f"Invalid strategy config in {path}: {', '.join(errors)}"
                )

            logger.info(
                "strategy_loaded",
                strategy_id=config.id,
                name=config.name,
                symbol=config.symbol,
            )

            return config

        except yaml.YAMLError as e:
            raise StrategyLoaderError(f"YAML parse error in {path}: {e}") from e
        except Exception as e:
            if isinstance(e, StrategyLoaderError):
                raise
            raise StrategyLoaderError(f"Failed to load {path}: {e}") from e

    @staticmethod
    def load_all(directory: Path) -> list[StrategyConfig]:
        """Load all strategy configurations from a directory.

        Args:
            directory: Path to directory containing YAML files

        Returns:
            List of StrategyConfig instances
        """
        if not directory.exists():
            logger.warning("strategies_directory_not_found", path=str(directory))
            return []

        if not directory.is_dir():
            raise StrategyLoaderError(f"Not a directory: {directory}")

        configs = []
        errors = []

        for path in sorted(directory.glob("*.yaml")):
            try:
                config = StrategyLoader.load(path)
                configs.append(config)
            except StrategyLoaderError as e:
                errors.append(str(e))
                logger.warning("strategy_load_failed", path=str(path), error=str(e))

        # Also check .yml files
        for path in sorted(directory.glob("*.yml")):
            try:
                config = StrategyLoader.load(path)
                configs.append(config)
            except StrategyLoaderError as e:
                errors.append(str(e))
                logger.warning("strategy_load_failed", path=str(path), error=str(e))

        logger.info(
            "strategies_loaded",
            count=len(configs),
            errors=len(errors),
            directory=str(directory),
        )

        return configs

    @staticmethod
    def validate_yaml(content: str) -> tuple[bool, str]:
        """Validate YAML content without loading as strategy.

        Args:
            content: YAML string content

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            data = yaml.safe_load(content)
            if not data:
                return False, "Empty YAML content"

            config = StrategyConfig.from_dict(data)
            errors = config.validate()

            if errors:
                return False, "; ".join(errors)

            return True, ""

        except yaml.YAMLError as e:
            return False, f"YAML parse error: {e}"
        except Exception as e:
            return False, str(e)
