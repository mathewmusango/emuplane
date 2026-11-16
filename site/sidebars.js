module.exports = {
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Getting started',
      collapsed: false,
      items: ['getting-started/quickstart', 'getting-started/console'],
    },
    {
      type: 'category',
      label: 'Concepts',
      collapsed: false,
      items: ['concepts/architecture', 'concepts/tenancy'],
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
      items: ['reference/control-api', 'reference/s3-coverage'],
    },
    'comparison/ministack-and-the-fork',
  ],
}
