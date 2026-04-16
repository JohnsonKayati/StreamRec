const ADJECTIVES = [
  'Premium',
  'Classic',
  'Ultra',
  'Pro',
  'Deluxe',
  'Essential',
  'Smart',
  'Elite',
  'Advanced',
  'Signature',
];

const PRODUCTS = [
  'Headphones',
  'Laptop',
  'Smart Watch',
  'Camera',
  'Backpack',
  'Speaker',
  'Keyboard',
  'Desk Lamp',
  'Tablet',
  'Charger',
];

const CATEGORIES = [
  'Electronics',
  'Books',
  'Clothing',
  'Home & Kitchen',
  'Sports',
  'Toys',
  'Beauty',
  'Automotive',
  'Music',
  'Movies',
];

export interface FakeMetadata {
  name: string;
  category: string;
}

/**
 * Deterministically maps an item_id to a fake product name and category.
 * item_0237 → e.g. "Pro Smart Watch · Sports"
 *
 * Uses the numeric part of the ID to index into ADJECTIVES, PRODUCTS, CATEGORIES
 * so the same item_id always produces the same display name.
 */
export function getFakeMetadata(itemId: string): FakeMetadata {
  const num = parseInt(itemId.replace(/\D/g, ''), 10) || 0;

  const adj = ADJECTIVES[num % ADJECTIVES.length];
  const product = PRODUCTS[Math.floor(num / ADJECTIVES.length) % PRODUCTS.length];
  const category =
    CATEGORIES[
      Math.floor(num / (ADJECTIVES.length * PRODUCTS.length)) %
        CATEGORIES.length
    ];

  return { name: `${adj} ${product}`, category };
}
