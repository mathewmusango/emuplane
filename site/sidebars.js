module.exports = {
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: ['getting-started/quickstart', 'getting-started/access', 'getting-started/console', 'getting-started/access-keys'],
    },
    {
      type: 'category',
      label: 'Concepts',
      collapsed: false,
      items: ['concepts/architecture', 'concepts/tenancy', 'concepts/extensions'],
    },
    {
      type: 'category',
      label: 'Guides',
      collapsed: false,
      items: ['guides/s3'],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: [
        'reference/control-api',
        'reference/s3-coverage',
        'reference/configuration',
        'reference/limits',
      ],
    },
  ],
}
