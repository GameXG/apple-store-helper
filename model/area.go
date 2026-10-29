package model

type Area struct {
	Title     string
	Locale    string
	ShortCode string
}

/**
 * Areas 地区
 * 中国大陆: CN/zh_CN
 * 中国澳门: MO/zh_MO
 *
 * ProductsJson 是 productSelectionData 对象的数组，包含各系列的当地 SKU、颜色和容量。
 * 同一 SKU 的不同购买方案只需保留一个 products 条目。
 * 打开购买页面，在开发者工具 Elements 面板中搜索 productSelectionData 提取值
 * Example URLs:
 * - https://www.apple.com.cn/shop/buy-iphone/iphone-18-pro
 * - https://www.apple.com.cn/shop/buy-iphone/iphone-duo
 */
var Areas = []Area{
	{
		Title:     "中国大陆",
		Locale:    "zh_CN",
		ShortCode: "cn",
	},
	{
		Title:     "中国香港",
		ShortCode: "hk-zh", // hk
		Locale:    "zh_HK",
	},
	{
		Title:     "中国台湾",
		ShortCode: "tw",
		Locale:    "zh_TW",
	},
	{
		Title:     "Singapore",
		ShortCode: "sg",
		Locale:    "en_SG",
	},
	{
		Title:     "日本",
		ShortCode: "jp",
		Locale:    "ja_JP",
	},
	{
		Title:     "Australia",
		ShortCode: "au",
		Locale:    "en_AU",
	},
	{
		Title:     "Malaysia",
		ShortCode: "my",
		Locale:    "en_MY",
	},
}
