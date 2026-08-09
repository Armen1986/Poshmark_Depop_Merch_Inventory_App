# Poshmark Depop Merch Inventory App
# Inventory App

A small Python command-line inventory manager for tracking items and quantities.

## Features

- Add new inventory items
- Update item quantities
- Remove items from inventory
- List all inventory items with quantity and description
- Persist inventory to a local JSON file

## Requirements

- Python 3.9+

## Usage

Run the app from the repository root:

```bash
python app.py add "Widget" 10 --description "Standard widget"
python app.py update "Widget" 15
python app.py remove "Widget"
python app.py list
```

### Commands

- `add <name> <quantity>`: Add a new item or increase quantity for an existing item.
- `update <name> <quantity>`: Set the exact quantity for an existing item.
- `remove <name>`: Remove an item from inventory.
- `list`: Show all inventory items.

## Data Storage

Inventory data is stored in `inventory.json` in the repository directory. The file is created automatically when the first command runs.

## Example

```bash
python app.py add "Laptop" 5 --description "Office laptops"
python app.py list
```
