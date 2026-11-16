// Where a service's rows open: S3 Tables and S3 Files are children of S3, so they map to its pages, not `/s3tables/home`.

export const SERVICE_ROUTES = {
  s3tables: '/s3/table-buckets',
  s3files: '/s3/files',
}

export function serviceHref(name) {
  return SERVICE_ROUTES[name] || `/${name}/home`
}
