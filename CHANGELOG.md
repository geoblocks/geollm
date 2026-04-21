# Changelog

## 0.1.0 (2026-04-21)


### Features

* add datasources ([5fa2731](https://github.com/geoblocks/etter/commit/5fa2731e8b26dd87d53782b1cf6318274b54882a))
* add Docker support with Dockerfile and docker-compose configuration ([8c84c9e](https://github.com/geoblocks/etter/commit/8c84c9e814ee84d8d66b36318cb1e95184bce419))
* add MCP App ([dbbe8fa](https://github.com/geoblocks/etter/commit/dbbe8fa43a3ba4a1651761079e3d439672a13390))
* add rapidfuzz ([2d954b5](https://github.com/geoblocks/etter/commit/2d954b55540f4662793a7de6197edf3194307474))
* add sponsor ([a90fa2e](https://github.com/geoblocks/etter/commit/a90fa2e20018b864a4498296b4ca92243f096337))
* add sponsor ([ee6d29b](https://github.com/geoblocks/etter/commit/ee6d29b10cac655f1ff11fdffa46cf4d938d96f2))
* add support for IGN BD-CARTO data source ([a206c16](https://github.com/geoblocks/etter/commit/a206c16104759d584e50f075df76bf1d5f1c4f69))
* add timing to /api/query/stream ([fb16004](https://github.com/geoblocks/etter/commit/fb160046a7178f59c4c3c555a8669988a802ac4c))
* add timing to /api/query/stream ([3a5acc2](https://github.com/geoblocks/etter/commit/3a5acc21da935a32a4ea4ceb0b0523c34fbc0ac5))
* better near relation for polygon ([6b51ac2](https://github.com/geoblocks/etter/commit/6b51ac232647338c77dcd60417f09cd37cc2bafe))
* better near relation for polygon ([0e654f0](https://github.com/geoblocks/etter/commit/0e654f041a9d6cd4ce900a60dd7d4492fe379e02))
* **datasources:** add generic PostGISDataSource ([09bd020](https://github.com/geoblocks/etter/commit/09bd0203479d1a6c1b3e0c37a99f6e831cf5b132))
* **datasources:** add type mapping support for PostGISDataSource ([34dfeb4](https://github.com/geoblocks/etter/commit/34dfeb4ddea9d492aec786770a60e4b2a35fe845))
* **datasources:** add unaccent support for name matching in PostGISDataSource ([14da5f3](https://github.com/geoblocks/etter/commit/14da5f328754d9830e1e4345f4279e86610a86a3))
* **docs:** add VitePress site with guides and CI deployment ([aeaa203](https://github.com/geoblocks/etter/commit/aeaa203adcaf826ab5b566b5410babcdc9abf646))
* enhance apply_spatial_relation with spatial_config parameter ([11fdeef](https://github.com/geoblocks/etter/commit/11fdeef710c96e82b8589c3912b5db19b7f4111e))
* enhance PostGISDataSource with unaccent support and improve fuzzy search logic ([b9d0630](https://github.com/geoblocks/etter/commit/b9d0630ec9a5a9ff3d351eb42000090fdff84284))
* enhance type filtering in SwissNames3DSource with hierarchical matching ([382fbc0](https://github.com/geoblocks/etter/commit/382fbc0b155060f3d498f439ea44dc8fbf50993f))
* implement GeoLLM MCP server with query parsing functionality ([93a559e](https://github.com/geoblocks/etter/commit/93a559e24f61be8be3b16cbb62c2cfeb4c8103f0))
* implement streaming query processing with real-time reasoning ([ceb5009](https://github.com/geoblocks/etter/commit/ceb50095ee92abf4b2e400f2056649322237ce57))
* implement streaming query processing with real-time reasoning ([a758e57](https://github.com/geoblocks/etter/commit/a758e57b2f154d5b16ec80869ee66642cfe7f722))
* make sur doc is up to date ([c233589](https://github.com/geoblocks/etter/commit/c23358942c0d3cb714757e10f9ffaa84460765a4))
* make sur doc is up to date ([65cbb49](https://github.com/geoblocks/etter/commit/65cbb49d227c729962b763d30465b0876f13cda8))
* nicer repl ([9f1e3e6](https://github.com/geoblocks/etter/commit/9f1e3e61dc7432e2b80fb644b668e3938ee6d9c1))
* nicer repl ([8f9fdba](https://github.com/geoblocks/etter/commit/8f9fdbaafcf2fd26ff385fc3b321dc6e79b45fb1))
* right/left bank ([58e209b](https://github.com/geoblocks/etter/commit/58e209b834155e908b9e0b157689f916abeaafa5))
* right/left bank ([8424d26](https://github.com/geoblocks/etter/commit/8424d2667b645a812e8e2f2104427f5e72ee2c32))
* update Makefile to improve installation and demo commands ([77fb4c5](https://github.com/geoblocks/etter/commit/77fb4c5bce83d9d880b907cb42085c1bc82c91ff))


### Bug Fixes

* handle MultiLineString geometries for right and left buffer ([e07364e](https://github.com/geoblocks/etter/commit/e07364eceb867b03677254cdd7be152fa0fa9a39))
* improve database connection error handling in PostGISDataSource ([aef33a4](https://github.com/geoblocks/etter/commit/aef33a45c4f4f0b97e7e208f8ba6fc30fc69f4d3))
* remove deduplication from search results in CompositeDataSource ([6860f24](https://github.com/geoblocks/etter/commit/6860f2416c35befa869e0476858df4bf4f700eb8))
* update doc ([0175ce2](https://github.com/geoblocks/etter/commit/0175ce24f1aaa850c8d186d0392a6f76e3759160))
* update GeoLLM server URL in mcp.json ([e4b4bc6](https://github.com/geoblocks/etter/commit/e4b4bc6fd88449e744815e176f22660d6e85926e))
* update LLM invocation to use asynchronous method ([352b0db](https://github.com/geoblocks/etter/commit/352b0dbcb146c6f92b795970295c99da550c2fea))


### Documentation

* add README for GeoLLM MCP App with architecture and setup instructions ([e2d282c](https://github.com/geoblocks/etter/commit/e2d282c752a1d826b99818a3ca9fe2fe5b5f0061))
* clarify Phase 2 is fully implemented with datasources ([e62cd57](https://github.com/geoblocks/etter/commit/e62cd57fe61b8ce8fe93a55cd9a317e2e08f6419))
* clarify search method description in CompositeDataSource ([6490343](https://github.com/geoblocks/etter/commit/64903434d955aa198a32049fd31616d9c60dc9f9))
* update README to include streaming support and usage examples ([72663ce](https://github.com/geoblocks/etter/commit/72663cee05d1d11f001a9cde5037d03e5abbb90b))
