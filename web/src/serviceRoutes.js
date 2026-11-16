// Where a service's rows open.
//
// Most services are pages of their own at `/<service>/home`. Two are not: S3
// Tables and S3 Files are children of S3 in this console, and the sidebar keeps
// them under *Amazon S3*, so anything that lists them by name — All services, the
// services menu, the dashboard — has to send the caller to the S3 page instead of
// a `/s3tables/home` that does not exist.

export const SERVICE_ROUTES = {
  s3tables: '/s3/table-buckets',
  s3files: '/s3/files',
}

export function serviceHref(name) {
  return SERVICE_ROUTES[name] || `/${name}/home`
}
