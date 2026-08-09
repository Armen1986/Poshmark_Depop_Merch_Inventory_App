#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Dict, Any

DATA_FILE = Path(__file__).with_name("inventory.json")


def load_inventory() -> Dict[str, Any]:
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_inventory(inventory: Dict[str, Any]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(inventory, file, indent=2, ensure_ascii=False)


def add_item(name: str, quantity: int, description: str | None) -> None:
    inventory = load_inventory()
    item = inventory.get(name, {"quantity": 0, "description": description or ""})
    item["quantity"] = item.get("quantity", 0) + quantity
    if description:
        item["description"] = description
    inventory[name] = item
    save_inventory(inventory)
    print(f"Added {quantity} to '{name}'. New quantity: {item['quantity']}")


def update_item(name: str, quantity: int) -> None:
    inventory = load_inventory()
    if name not in inventory:
        raise ValueError(f"Item '{name}' does not exist.")
    inventory[name]["quantity"] = quantity
    save_inventory(inventory)
    print(f"Updated '{name}' quantity to {quantity}.")


def remove_item(name: str) -> None:
    inventory = load_inventory()
    if name not in inventory:
        raise ValueError(f"Item '{name}' does not exist.")
    inventory.pop(name)
    save_inventory(inventory)
    print(f"Removed '{name}' from inventory.")


def list_items() -> None:
    inventory = load_inventory()
    if not inventory:
        print("Inventory is empty.")
        return
    print("Inventory:")
    for name, details in sorted(inventory.items()):
        quantity = details.get("quantity", 0)
        description = details.get("description", "")
        row = f"- {name}: {quantity}"
        if description:
            row += f" ({description})"
        print(row)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory app CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add an item to inventory")
    add_parser.add_argument("name", type=str, help="Item name")
    add_parser.add_argument("quantity", type=int, help="Quantity to add")
    add_parser.add_argument("--description", type=str, help="Item description", default="")

    update_parser = subparsers.add_parser("update", help="Update item quantity")
    update_parser.add_argument("name", type=str, help="Item name")
    update_parser.add_argument("quantity", type=int, help="New quantity")

    remove_parser = subparsers.add_parser("remove", help="Remove an item")
    remove_parser.add_argument("name", type=str, help="Item name")

    subparsers.add_parser("list", help="List all items")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "add":
            add_item(args.name, args.quantity, args.description)
        elif args.command == "update":
            update_item(args.name, args.quantity)
        elif args.command == "remove":
            remove_item(args.name)
        elif args.command == "list":
            list_items()
        return 0
    except ValueError as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
