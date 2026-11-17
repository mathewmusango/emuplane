const config = {
  title: 'Emuplane',
  tagline: 'A console and control plane for local AWS emulation',
  favicon: 'img/mark.png',

  url: 'https://mathewmusango.github.io',
  baseUrl: '/emuplane/',
  organizationName: 'mathewmusango',
  projectName: 'emuplane',
  trailingSlash: false,

  onBrokenLinks: 'throw',

  markdown: {
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },
  // Diagram support for the fenced ```mermaid blocks.
  themes: ['@docusaurus/theme-mermaid'],

  // Offline full-text search, built with the site.
  plugins: [
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        indexBlog: false,
        docsRouteBasePath: '/docs',
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: require.resolve('./sidebars.js'),
          editUrl: 'https://github.com/mathewmusango/emuplane/tree/main/',
          showLastUpdateTime: false,
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      },
    ],
  ],

  themeConfig: {
    navbar: {
      title: 'Emuplane',
      logo: {
        alt: 'Emuplane',
        src: 'img/mark.png',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Docs',
        },
        {
          type: 'docsVersionDropdown',
          position: 'right',
        },
        {
          href: 'https://github.com/mathewmusango/emuplane',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            { label: 'Quickstart', to: '/docs/getting-started/quickstart' },
            { label: 'Architecture', to: '/docs/concepts/architecture' },
            { label: 'Control API', to: '/docs/reference/control-api' },
          ],
        },
        {
          title: 'Reference',
          items: [
            { label: 'S3 coverage', to: '/docs/reference/s3-coverage' },
          ],
        },
      ],
      copyright: `Emuplane documentation. Built with Docusaurus.`,
    },
    prism: {
      theme: require('prism-react-renderer').themes.github,
      darkTheme: require('prism-react-renderer').themes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'yaml', 'rust'],
    },
    // Follow the reader's system theme, with light as the default.
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
  },
}

module.exports = config
