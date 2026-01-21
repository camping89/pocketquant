"""Health check script for development environment."""

import asyncio
import sys

from rich.console import Console

console = Console(force_terminal=True, legacy_windows=False)


async def check_mongodb() -> bool:
    """Verify MongoDB is reachable with configured credentials."""
    from pymongo.asynchronous.mongo_client import AsyncMongoClient

    from src.config import get_settings

    settings = get_settings()
    try:
        client = AsyncMongoClient(str(settings.mongodb_url), serverSelectionTimeoutMS=2000)
        await client.server_info()
        await client.close()
        console.print("  [green]OK[/] MongoDB connected")
        return True
    except Exception as e:
        console.print(f"  [red]FAIL[/] MongoDB: {e}")
        return False


async def check_redis() -> bool:
    """Verify Redis is reachable."""
    import redis.asyncio as redis

    from src.config import get_settings

    settings = get_settings()
    try:
        client = redis.from_url(str(settings.redis_url), socket_timeout=2)
        await client.ping()
        await client.aclose()
        console.print("  [green]OK[/] Redis connected")
        return True
    except Exception as e:
        console.print(f"  [red]FAIL[/] Redis: {e}")
        return False


def check_docker_containers() -> bool:
    """Check if required Docker containers are healthy."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker/compose.yml", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            console.print("  [red]FAIL[/] Docker compose not available")
            return False

        import json

        containers = [json.loads(line) for line in result.stdout.strip().split("\n") if line]
        all_healthy = True

        for c in containers:
            name = c.get("Name", "unknown")
            status = c.get("Health", c.get("State", "unknown"))
            if status == "healthy" or (status == "" and c.get("State") == "running"):
                console.print(f"  [green]OK[/] {name}: running")
            else:
                console.print(f"  [red]FAIL[/] {name}: {status}")
                all_healthy = False

        return all_healthy
    except FileNotFoundError:
        console.print("  [red]FAIL[/] Docker not installed")
        return False
    except Exception as e:
        console.print(f"  [red]FAIL[/] Docker check failed: {e}")
        return False


async def main() -> int:
    console.print("\n[bold]Checking development environment...[/]\n")

    console.print("[cyan]Docker Containers:[/]")
    docker_ok = check_docker_containers()

    console.print("\n[cyan]Service Connections:[/]")
    mongo_ok = await check_mongodb()
    redis_ok = await check_redis()

    console.print()
    if docker_ok and mongo_ok and redis_ok:
        console.print("[bold green]OK All checks passed[/]\n")
        return 0
    else:
        console.print("[bold red]FAIL Some checks failed[/]\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
