# insightsApiSearch

insightsApiSearch是一个的搜索引擎。它提供了一个页面支持搜索接口、数据库连接、Git项目等信息。设计用于帮助互联网公司的工作中，各类人员能够实时搜索，稳定，可靠，快速地找到项目或代码的信息，从而提升工作效率。

例如，项目经理在发现某些接口出现报错时，通过该平台查询到接口的开发人员、隶属于哪一个开发项目中，从而快速对接工作；数据库管理也可以在需要修改数据库时，快速查询到该数据库被哪些项目使用到，从而不遗漏地通知到这些项目负责人，做到不影响这些项目的运行；前端人员可以通过它查询到每个接口的使用文档，从而减少相关的对接的工作；后端人员亦可以查询到某个接口被哪些项目调用过，从而保证修改接口后依然可以支持这些项目。
LiGeFlag项目包含3个部分，第一个是后端进行代码扫描的系统，它将定时扫描出项目代码中的接口、数据库链接等信息，并存入数据库。第二个部分提供Web接口服务，用于提供给前端进行数据展示。第三个部分是前端，用于提供搜索服务及数据展示。

![image](https://raw.githubusercontent.com/insightsvalue/insightsApiSearch/main/%E6%9E%B6%E6%9E%84.png)
![image](https://github.com/insightsvalue/insightsApiSearch/blob/main/%E6%88%AA%E5%B1%8F1.png?raw=true)
![image](https://github.com/insightsvalue/insightsApiSearch/blob/main/%E6%88%AA%E5%B1%8F2.png?raw=true)
