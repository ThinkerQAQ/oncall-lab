namespace go metadata

struct GetMetadataRequest {
    1: required string article_id,
    2: optional i32 delay_ms,
}

struct GetMetadataResponse {
    1: required string article_id,
    2: required string title,
}

service MetadataService {
    GetMetadataResponse GetMetadata(1: GetMetadataRequest req),
}
